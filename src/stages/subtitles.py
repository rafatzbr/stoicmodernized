"""Subtitle generation stage module."""

import re
import subprocess
from pathlib import Path
from typing import Optional

from src.config import settings
from src.models import SubtitleSegment, SubtitleResult
from src.utils import load_json, save_json


class SubtitleStage:
    """Handles subtitle generation."""

    TIMED_BLOCK_RE = re.compile(
        r"^\[(?P<start>\d+:\d{2})-(?P<end>\d+:\d{2})\]\s*(?P<title>.+?)\n(?P<body>.*?)(?=\n\[\d+:\d{2}-\d+:\d{2}\]|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    SIMPLE_SRT_RE = re.compile(
        r"(?P<index>\d+)\s+\n?(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2},\d{3})\s+\n?(?P<text>.*?)(?=\n\s*\n|\Z)",
        re.DOTALL,
    )

    def __init__(self, job_id: str, mock: bool = False):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.job_dir = settings.jobs_dir / job_id
        self.subtitles_dir = self.job_dir / "subtitles"
        self.scenes_dir = self.job_dir / "scenes"
        self.audio_dir = self.job_dir / "audio"

    async def run(self, script_data: dict, audio_path: Optional[str] = None) -> SubtitleResult:
        self.subtitles_dir.mkdir(parents=True, exist_ok=True)
        return await self._generate(script_data, audio_path)

    async def _generate(
        self, script_data: dict, audio_path: Optional[str] = None
    ) -> SubtitleResult:
        audio_duration = self._get_audio_duration(audio_path) if audio_path else None
        segments = self._load_edge_tts_segments()
        if not segments:
            scene_plan = self._load_scene_plan()
            segments = self._segments_from_scene_plan(scene_plan, audio_duration)
        if not segments:
            narration = script_data.get("narration", "")
            segments = self._parse_narration_to_segments(narration, audio_duration)
        segments = self._polish_segments(segments, audio_duration)
        self._retime_scene_plan_from_vtt_matches(segments, audio_duration)
        srt_content = self._format_srt(segments)

        srt_path = self.subtitles_dir / "subtitles.srt"
        json_path = self.subtitles_dir / "subtitles.json"

        srt_path.write_text(srt_content, encoding="utf-8")
        save_json({"segments": [segment.model_dump() for segment in segments]}, json_path)

        return SubtitleResult(
            srt_content=srt_content,
            segments=segments,
            srt_path=str(srt_path),
            json_path=str(json_path),
        )

    def _load_edge_tts_segments(self) -> list[SubtitleSegment]:
        vtt_path = self.audio_dir / "narration.vtt"
        if not vtt_path.exists():
            return []
        try:
            text = vtt_path.read_text(encoding="utf-8")
        except Exception:
            return []

        segments: list[SubtitleSegment] = []
        for match in self.SIMPLE_SRT_RE.finditer(text.strip()):
            raw_text = " ".join(line.strip() for line in match.group("text").splitlines() if line.strip())
            if not raw_text:
                continue
            segments.append(
                SubtitleSegment(
                    start_time=self._parse_hhmmss_ms(match.group("start")),
                    end_time=self._parse_hhmmss_ms(match.group("end")),
                    text=self._clean_subtitle_text(raw_text),
                )
            )
        return segments

    def _load_scene_plan(self) -> Optional[dict]:
        scene_path = self.scenes_dir / "scenes.json"
        if not scene_path.exists():
            return None
        try:
            return load_json(scene_path)
        except Exception:
            return None

    def _retime_scene_plan_from_vtt_matches(
        self, segments: list[SubtitleSegment], audio_duration: Optional[float]
    ) -> None:
        if not segments or audio_duration is None or audio_duration <= 0:
            return

        scene_plan = self._load_scene_plan()
        if not isinstance(scene_plan, dict):
            return

        scenes = scene_plan.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            return

        spoken_scenes = [
            scene
            for scene in scenes
            if isinstance(scene, dict)
            and str(scene.get("narration_segment", "")).lower() not in {"intro branding", "outro branding"}
        ]
        if not spoken_scenes:
            return

        matched_starts: list[float] = []
        search_index = 0
        for scene in spoken_scenes:
            first_phrase = self._first_phrase(scene.get("narration_segment", ""))
            if not first_phrase:
                return
            match_index = self._find_matching_segment_index(segments, first_phrase, search_index)
            if match_index is None:
                return
            matched_starts.append(segments[match_index].start_time)
            search_index = match_index

        for index, scene in enumerate(spoken_scenes):
            start = matched_starts[index]
            end = matched_starts[index + 1] if index + 1 < len(matched_starts) else audio_duration
            scene["start_time"] = round(start, 3)
            scene["end_time"] = round(max(start + 0.05, end), 3)

        scene_plan["total_duration"] = round(audio_duration, 3)
        save_json(scene_plan, self.scenes_dir / "scenes.json")

    def _find_matching_segment_index(
        self, segments: list[SubtitleSegment], phrase: str, start_index: int
    ) -> Optional[int]:
        target = self._match_key(phrase)
        if not target:
            return None
        for index in range(start_index, len(segments)):
            haystack = self._match_key(segments[index].text)
            if target in haystack or haystack in target:
                return index
        return None

    def _match_key(self, text: str) -> str:
        normalized = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _first_phrase(self, text: object) -> str:
        if not isinstance(text, str):
            return ""
        clean = self._clean_subtitle_text(text)
        phrases = self._split_into_phrases(clean)
        return phrases[0] if phrases else clean

    def _segments_from_scene_plan(
        self, scene_plan: Optional[dict], audio_duration: Optional[float] = None
    ) -> list[SubtitleSegment]:
        if not isinstance(scene_plan, dict):
            return []
        scenes = scene_plan.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            return []

        spoken_scenes = []
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            text = self._clean_scene_text(scene.get("narration_segment"))
            if not text or text.lower() in {"intro branding", "outro branding"}:
                continue
            try:
                start = float(scene.get("start_time", 0.0))
                end = float(scene.get("end_time", start))
            except (TypeError, ValueError):
                continue
            if end <= start:
                continue
            spoken_scenes.append((start, end, text))

        if not spoken_scenes:
            return []

        if audio_duration is not None:
            last_end = max(end for _, end, _ in spoken_scenes)
            if last_end > 0:
                scale = audio_duration / last_end
                if 0.85 <= scale <= 1.25:
                    spoken_scenes = [
                        (round(start * scale, 3), round(end * scale, 3), text)
                        for start, end, text in spoken_scenes
                    ]

        segments: list[SubtitleSegment] = []
        for start, end, text in spoken_scenes:
            phrases = self._split_into_phrases(text)
            if not phrases:
                continue
            segments.extend(self._timed_phrases_to_segments(start, end, phrases))
        return segments

    def _parse_narration_to_segments(
        self, narration: str, audio_duration: Optional[float] = None
    ) -> list[SubtitleSegment]:
        timed_segments = self._parse_timed_blocks(narration, audio_duration)
        if timed_segments:
            return timed_segments

        text_lines = [line.strip() for line in narration.split("\n") if line.strip() and not line.startswith("[")]
        phrases: list[str] = []
        for line in text_lines:
            phrases.extend(self._split_into_phrases(line))

        phrases = [p for p in phrases if p]
        if not phrases:
            return []

        total_words = sum(max(1, len(phrase.split())) for phrase in phrases)
        effective_duration = max(audio_duration or 0.0, len(phrases) * 0.8)
        current_time = 0.0
        segments: list[SubtitleSegment] = []

        for index, phrase in enumerate(phrases):
            words = max(1, len(phrase.split()))
            duration = effective_duration * (words / total_words)
            duration = min(max(duration, 0.8), 2.2)
            if index == len(phrases) - 1:
                end_time = effective_duration
            else:
                end_time = min(effective_duration, current_time + duration)
            segments.append(
                SubtitleSegment(
                    start_time=round(current_time, 2),
                    end_time=round(end_time, 2),
                    text=phrase,
                )
            )
            current_time = end_time

        return segments

    def _parse_timed_blocks(
        self, narration: str, audio_duration: Optional[float] = None
    ) -> list[SubtitleSegment]:
        matches = list(self.TIMED_BLOCK_RE.finditer(narration.strip()))
        if not matches:
            return []

        blocks: list[tuple[float, float, list[str]]] = []
        last_end = 0.0
        for match in matches:
            start = self._parse_mmss(match.group("start"))
            end = self._parse_mmss(match.group("end"))
            if audio_duration is not None:
                start = min(start, audio_duration)
                end = min(end, audio_duration)
            if end <= start:
                continue
            phrases = self._split_into_phrases(self._normalize_block_text(match.group("body")))
            phrases = [phrase for phrase in phrases if phrase]
            if not phrases:
                continue
            blocks.append((start, end, phrases))
            last_end = max(last_end, end)

        if not blocks:
            return []

        if audio_duration and last_end > 0:
            scale = audio_duration / last_end
            if 0.85 <= scale <= 1.25:
                blocks = [
                    (round(start * scale, 3), round(end * scale, 3), phrases)
                    for start, end, phrases in blocks
                ]

        segments: list[SubtitleSegment] = []
        for start, end, phrases in blocks:
            segments.extend(self._timed_phrases_to_segments(start, end, phrases))
        return segments

    def _timed_phrases_to_segments(self, start: float, end: float, phrases: list[str]) -> list[SubtitleSegment]:
        total_words = sum(max(1, len(phrase.split())) for phrase in phrases)
        available = max(0.1, end - start)
        current_time = start
        segments: list[SubtitleSegment] = []

        for index, phrase in enumerate(phrases):
            words = max(1, len(phrase.split()))
            raw_duration = available * (words / total_words)
            duration = min(max(raw_duration, 0.7), 3.0)
            if index == len(phrases) - 1:
                end_time = end
            else:
                end_time = min(end, current_time + duration)
            segments.append(
                SubtitleSegment(
                    start_time=round(current_time, 2),
                    end_time=round(end_time, 2),
                    text=phrase,
                )
            )
            current_time = end_time
        return segments

    def _clean_scene_text(self, value: object) -> str:
        if not isinstance(value, str):
            return ""
        text = value.replace("\r", " ").replace("\n", " ").strip()
        text = re.sub(r"\s+", " ", text)
        return self._clean_subtitle_text(text)

    def _normalize_block_text(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return self._clean_subtitle_text(" ".join(lines))

    def _parse_mmss(self, value: str) -> float:
        minutes, seconds = value.split(":", 1)
        return int(minutes) * 60 + int(seconds)

    def _parse_hhmmss_ms(self, value: str) -> float:
        hours, minutes, rest = value.split(":")
        seconds, millis = rest.split(",")
        return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0

    def _split_into_phrases(self, line: str) -> list[str]:
        chunks = re.split(r"(?<=[,;:.!?—])\s+", line)
        phrases: list[str] = []
        for chunk in chunks:
            words = chunk.split()
            if len(words) <= 6:
                phrases.append(chunk.strip())
                continue
            current: list[str] = []
            for word in words:
                current.append(word)
                if len(current) >= 4:
                    phrases.append(" ".join(current).strip())
                    current = []
            if current:
                phrases.append(" ".join(current).strip())
        return [phrase for phrase in phrases if phrase]

    def _get_audio_duration(self, audio_path: str) -> Optional[float]:
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(probe.stdout.strip())
        except Exception:
            return None

    def _format_srt(self, segments: list[SubtitleSegment]) -> str:
        srt_lines = []
        for i, seg in enumerate(segments, 1):
            srt_lines.append(str(i))
            srt_lines.append(
                f"{self._format_time(seg.start_time)} --> {self._format_time(seg.end_time)}"
            )
            srt_lines.append(seg.text)
            srt_lines.append("")
        return "\n".join(srt_lines)

    def _format_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        whole_seconds = int(seconds % 60)
        ms = int(round((seconds - int(seconds)) * 1000))
        if ms >= 1000:
            whole_seconds += 1
            ms = 0
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{ms:03d}"

    def save_subtitles(self, result: SubtitleResult) -> None:
        _ = result

    def load_subtitles(self) -> Optional[SubtitleResult]:
        json_path = self.subtitles_dir / "subtitles.json"
        srt_path = self.subtitles_dir / "subtitles.srt"
        if not json_path.exists():
            return None

        data = load_json(json_path)
        srt_content = srt_path.read_text(encoding="utf-8") if srt_path.exists() else ""
        return SubtitleResult(
            srt_content=srt_content,
            segments=[SubtitleSegment(**s) for s in data.get("segments", [])],
            srt_path=str(srt_path),
            json_path=str(json_path),
        )

    def _clean_subtitle_text(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.replace("\r", " ").replace("\n", " ")).strip()
        cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
        cleaned = self._strip_unmatched_quotes(cleaned)
        return cleaned

    def _strip_unmatched_quotes(self, text: str) -> str:
        quote_positions = [
            index
            for index, char in enumerate(text)
            if char in {"'", '"'} and not self._is_apostrophe(text, index)
        ]
        if len(quote_positions) % 2 == 0:
            return text

        chars = list(text)
        remove_index = quote_positions[0]
        chars.pop(remove_index)
        return "".join(chars).strip()

    def _is_apostrophe(self, text: str, index: int) -> bool:
        if text[index] != "'":
            return False
        prev_char = text[index - 1] if index > 0 else ""
        next_char = text[index + 1] if index + 1 < len(text) else ""
        return prev_char.isalpha() and next_char.isalpha()

    def _polish_segments(
        self, segments: list[SubtitleSegment], audio_duration: Optional[float]
    ) -> list[SubtitleSegment]:
        if not segments:
            return []

        polished: list[SubtitleSegment] = []
        running_time = 0.0
        for segment in segments:
            text = self._clean_subtitle_text(segment.text)
            if not text:
                continue

            start = max(0.0, segment.start_time, running_time)
            end = max(start + 0.05, segment.end_time)
            if audio_duration is not None:
                start = min(start, audio_duration)
                end = min(end, audio_duration)
            if end <= start:
                continue

            polished.append(
                SubtitleSegment(
                    start_time=round(start, 3),
                    end_time=round(end, 3),
                    text=text,
                    words=segment.words,
                )
            )
            running_time = polished[-1].end_time

        if audio_duration is not None and polished:
            polished[-1].end_time = round(min(polished[-1].end_time, audio_duration), 3)
            if 0.0 < audio_duration - polished[-1].end_time <= 0.25:
                polished[-1].end_time = round(audio_duration, 3)

        return polished
