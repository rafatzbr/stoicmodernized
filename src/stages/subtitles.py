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

    def __init__(self, job_id: str, mock: bool = False):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.job_dir = settings.jobs_dir / job_id
        self.subtitles_dir = self.job_dir / "subtitles"

    async def run(self, script_data: dict, audio_path: Optional[str] = None) -> SubtitleResult:
        self.subtitles_dir.mkdir(parents=True, exist_ok=True)
        return await self._generate(script_data, audio_path)

    async def _generate(
        self, script_data: dict, audio_path: Optional[str] = None
    ) -> SubtitleResult:
        narration = script_data.get("narration", "")
        audio_duration = self._get_audio_duration(audio_path) if audio_path else None
        segments = self._parse_narration_to_segments(narration, audio_duration)
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

    def _parse_narration_to_segments(
        self, narration: str, audio_duration: Optional[float] = None
    ) -> list[SubtitleSegment]:
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
