"""Subtitle generation stage module."""

import re
import subprocess
from pathlib import Path
from typing import Optional

from src.config import settings
from src.models import SubtitleSegment, SubtitleResult
from src.subtitle_timing import (
    TimedCue,
    TimedWord,
    apply_readability_windows,
    group_words_into_readable_cues,
    parse_webvtt_cues,
    write_webvtt,
)
from src.utils import load_json, save_json


class SubtitleStage:
    """Handles subtitle generation."""

    _asr_pipeline = None

    TIMED_BLOCK_RE = re.compile(
        r"^\[(?P<start>\d+:\d{2})-(?P<end>\d+:\d{2})\]\s*(?P<title>.+?)\n(?P<body>.*?)(?=\n\[\d+:\d{2}-\d+:\d{2}\]|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    SIMPLE_SRT_RE = re.compile(
        r"(?:WEBVTT\s+)?(?:\d+\s+)?(?P<start>\d{2}:\d{2}:\d{2}[\.,]\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2}[\.,]\d{3})\s+\n?(?P<text>.*?)(?=\n\s*\n|\Z)",
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
        if not segments and audio_path:
            transcript = self._alignment_transcript(script_data)
            if self._should_attempt_alignment(transcript, audio_path=audio_path):
                segments = self._aligned_segments(audio_path, transcript)
        if not segments and audio_path and settings.subtitle_asr_enabled:
            segments = self._transcribe_audio_segments(audio_path)
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
        vtt_path = self.subtitles_dir / "subtitles.vtt"
        json_path = self.subtitles_dir / "subtitles.json"

        srt_path.write_text(srt_content, encoding="utf-8")
        if self._should_write_vtt_sidecar():
            vtt_path.write_text(self._format_vtt(segments), encoding="utf-8")
        elif vtt_path.exists():
            vtt_path.unlink()
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

        return [
            SubtitleSegment(start_time=cue.start_time, end_time=cue.end_time, text=cue.text)
            for cue in parse_webvtt_cues(text, source="edge")
        ]

    def _load_scene_plan(self) -> Optional[dict]:
        scene_path = self.scenes_dir / "scenes.json"
        if not scene_path.exists():
            return None
        try:
            return load_json(scene_path)
        except Exception:
            return None

    def _transcribe_audio_segments(self, audio_path: str) -> list[SubtitleSegment]:
        try:
            pipe = self._get_asr_pipeline()
            result = pipe(
                audio_path,
                return_timestamps=True,
                generate_kwargs={
                    "task": "transcribe",
                    "language": settings.subtitle_asr_language,
                },
            )
        except Exception:
            return []

        chunks = result.get("chunks") if isinstance(result, dict) else None
        if not isinstance(chunks, list):
            return []

        segments: list[SubtitleSegment] = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            text = self._clean_subtitle_text(str(chunk.get("text") or ""))
            timestamps = chunk.get("timestamp") or chunk.get("timestamps")
            if not text or not isinstance(timestamps, (list, tuple)) or len(timestamps) != 2:
                continue
            start, end = timestamps
            if start is None or end is None:
                continue
            try:
                start_f = float(start)
                end_f = float(end)
            except (TypeError, ValueError):
                continue
            if end_f <= start_f:
                continue
            segments.append(
                SubtitleSegment(
                    start_time=round(start_f, 3),
                    end_time=round(end_f, 3),
                    text=text,
                )
            )
        return segments

    def _alignment_transcript(self, script_data: dict) -> str:
        scene_transcript = self._scene_plan_transcript()
        if scene_transcript:
            return scene_transcript

        narration = script_data.get("narration", "")
        parts: list[str] = []
        if isinstance(narration, str) and narration.strip():
            parts.extend(
                line.strip()
                for line in narration.splitlines()
                if line.strip() and not line.strip().startswith("[")
            )
        cta = str(script_data.get("cta") or "").strip()
        if cta and self._match_key(cta) not in self._match_key(" ".join(parts)):
            parts.append(cta)
        return self._clean_subtitle_text(" ".join(parts))

    def _scene_plan_transcript(self) -> str:
        scene_plan = self._load_scene_plan()
        if not isinstance(scene_plan, dict):
            return ""
        scenes = scene_plan.get("scenes")
        if not isinstance(scenes, list):
            return ""

        scene_texts: list[str] = []
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            text = self._clean_scene_text(scene.get("narration_segment"))
            if not text or text.lower() in {"intro branding", "outro branding"}:
                continue
            scene_texts.append(text)
        return self._clean_subtitle_text(" ".join(scene_texts))

    def _should_attempt_alignment(self, transcript: str, *, audio_path: Optional[str]) -> bool:
        if not audio_path or not transcript.strip():
            return False
        timing_mode = settings.tts_subtitles_timing.strip().lower().replace("_", "-")
        if timing_mode in {"align", "alignment", "forced-align", "forced-alignment", "stable-ts"}:
            return True
        return timing_mode == "auto" and bool(settings.tts_subtitles_alignment_enabled)

    def _aligned_segments(self, audio_path: str, transcript: str) -> list[SubtitleSegment]:
        words = self._align_transcript_words(audio_path, transcript)
        if not words:
            return []
        words = self._retime_transcript_words(words, transcript)
        template_segments = self._segments_from_edge_template(words)
        if template_segments:
            return template_segments
        cues = group_words_into_readable_cues(words, max_words=9, max_duration=3.2)
        cues = apply_readability_windows(cues, audio_duration=words[-1].end_time + 0.6 if words else None)
        return [self._subtitle_segment_from_timed_cue(cue) for cue in cues]

    def _segments_from_edge_template(self, words: list[TimedWord]) -> list[SubtitleSegment]:
        """Retiming Kokoro captions into EdgeTTS cue boundaries.

        EdgeTTS emits a VTT sidecar with the cue phrasing Rafael prefers. For
        audio-only providers such as Kokoro, use that sidecar as a text/structure
        template while taking cue start/end times from forced-aligned Kokoro word
        timings. This keeps the exact Edge-style line breaks without displaying
        subtitles on Edge's unrelated audio timeline.
        """

        template_path = self.audio_dir / "narration.edge.vtt"
        if not template_path.exists() or not words:
            return []
        try:
            template_cues = parse_webvtt_cues(template_path.read_text(encoding="utf-8"), source="edge-template")
        except Exception:
            return []
        if not template_cues:
            return []

        segments: list[SubtitleSegment] = []
        word_index = 0
        for cue in template_cues:
            cue_tokens = [token for token in cue.text.split() if token.strip()]
            if not cue_tokens:
                continue
            matched_words: list[TimedWord] = []
            for token in cue_tokens:
                token_key = self._normalize_alignment_token(token)
                match_index = None
                for candidate_index in range(word_index, min(len(words), word_index + 5)):
                    if token_key and token_key == self._normalize_alignment_token(words[candidate_index].text):
                        match_index = candidate_index
                        break
                if match_index is None:
                    if word_index < len(words):
                        matched_words.append(words[word_index])
                        word_index += 1
                    continue
                matched_words.extend(words[word_index : match_index + 1])
                word_index = match_index + 1

            if not matched_words:
                continue
            cue_segments = group_words_into_readable_cues(matched_words, max_words=9, max_duration=3.2)
            cue_segments = apply_readability_windows(
                cue_segments,
                audio_duration=words[-1].end_time + 0.6 if words else None,
            )
            segments.extend(self._subtitle_segment_from_timed_cue(cue_segment) for cue_segment in cue_segments)

        if len(segments) < max(1, int(len(template_cues) * 0.8)):
            return []
        return segments

    def _subtitle_segment_from_timed_cue(self, cue: TimedCue) -> SubtitleSegment:
        return SubtitleSegment(
            start_time=cue.start_time,
            end_time=cue.end_time,
            text=cue.text,
            words=[
                {
                    "text": word.text,
                    "start": word.start_time,
                    "end": word.end_time,
                    "source": word.source,
                    "confidence": word.confidence,
                }
                for word in cue.words
            ],
        )

    def _retime_transcript_words(self, aligned_words: list[TimedWord], transcript: str) -> list[TimedWord]:
        """Preserve script text while using aligner timings.

        Stable Whisper can omit tiny words such as articles. Building subtitles
        directly from those aligned words creates fragmented cue text. Keep the
        script as the text source and interpolate short spans for omitted words.
        """

        transcript_tokens = [token for token in transcript.split() if token.strip()]
        if not transcript_tokens or not aligned_words:
            return aligned_words

        retimed: list[TimedWord] = []
        aligned_index = 0
        previous_end = max(0.0, aligned_words[0].start_time)

        for token_index, token in enumerate(transcript_tokens):
            token_key = self._normalize_alignment_token(token)
            match_index = None
            search_end = min(len(aligned_words), aligned_index + 4)
            for candidate_index in range(aligned_index, search_end):
                candidate_key = self._normalize_alignment_token(aligned_words[candidate_index].text)
                if token_key and token_key == candidate_key:
                    match_index = candidate_index
                    break

            if match_index is not None:
                matched = aligned_words[match_index]
                start = max(previous_end, matched.start_time)
                end = max(start + 0.001, matched.end_time)
                retimed.append(
                    TimedWord(
                        text=token,
                        start_time=round(start, 3),
                        end_time=round(end, 3),
                        source=matched.source,
                        confidence=matched.confidence,
                    )
                )
                previous_end = end
                aligned_index = match_index + 1
                continue

            next_start = None
            for future_token in transcript_tokens[token_index + 1 : token_index + 5]:
                future_key = self._normalize_alignment_token(future_token)
                for candidate_index in range(aligned_index, min(len(aligned_words), aligned_index + 6)):
                    if future_key and future_key == self._normalize_alignment_token(aligned_words[candidate_index].text):
                        next_start = max(previous_end, aligned_words[candidate_index].start_time)
                        break
                if next_start is not None:
                    break

            if next_start is None:
                next_start = previous_end + 0.16

            gap = max(0.001, next_start - previous_end)
            start = previous_end
            end = min(next_start, previous_end + min(max(gap * 0.75, 0.08), 0.2))
            retimed.append(
                TimedWord(
                    text=token,
                    start_time=round(start, 3),
                    end_time=round(max(start + 0.001, end), 3),
                    source="alignment-inferred",
                )
            )
            previous_end = retimed[-1].end_time

        return retimed

    def _normalize_alignment_token(self, token: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", token.lower())

    def _align_transcript_words(self, audio_path: str, transcript: str) -> list[TimedWord]:
        aligner = settings.tts_subtitles_aligner.strip().lower()
        if aligner not in {"stable-ts", "stable_whisper", "stable-whisper"}:
            return []
        try:
            import stable_whisper
        except Exception:
            return []

        try:
            model = stable_whisper.load_model(settings.tts_subtitles_aligner_model)
            result = model.align(audio_path, transcript)
        except Exception:
            return []
        return self._timed_words_from_alignment_result(result)

    def _timed_words_from_alignment_result(self, result: object) -> list[TimedWord]:
        if hasattr(result, "to_dict"):
            try:
                result = result.to_dict()
            except Exception:
                return []
        if not isinstance(result, dict):
            return []

        raw_words: list[dict] = []
        if isinstance(result.get("words"), list):
            raw_words = [word for word in result["words"] if isinstance(word, dict)]
        elif isinstance(result.get("segments"), list):
            for segment in result["segments"]:
                if not isinstance(segment, dict):
                    continue
                words = segment.get("words")
                if isinstance(words, list):
                    raw_words.extend(word for word in words if isinstance(word, dict))

        timed_words: list[TimedWord] = []
        for word in raw_words:
            text = str(word.get("word") or word.get("text") or "").strip()
            try:
                start = float(word.get("start"))
                end = float(word.get("end"))
            except (TypeError, ValueError):
                continue
            if not text or end <= start:
                continue
            confidence_value = word.get("probability", word.get("confidence"))
            try:
                confidence = None if confidence_value is None else float(confidence_value)
            except (TypeError, ValueError):
                confidence = None
            timed_words.append(
                TimedWord(
                    text=text,
                    start_time=round(start, 3),
                    end_time=round(end, 3),
                    source="alignment",
                    confidence=confidence,
                )
            )
        return timed_words

    def _get_asr_pipeline(self):
        if SubtitleStage._asr_pipeline is not None:
            return SubtitleStage._asr_pipeline

        import torch
        from transformers import pipeline

        device = 0 if torch.cuda.is_available() else -1
        model_kwargs = {"low_cpu_mem_usage": True}
        if torch.cuda.is_available():
            model_kwargs["torch_dtype"] = torch.float16

        SubtitleStage._asr_pipeline = pipeline(
            "automatic-speech-recognition",
            model=settings.subtitle_asr_model,
            chunk_length_s=settings.subtitle_asr_chunk_length_s,
            device=device,
            model_kwargs=model_kwargs,
        )
        return SubtitleStage._asr_pipeline

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

        spoken_scene_entries = [
            (index, scene)
            for index, scene in enumerate(scenes)
            if isinstance(scene, dict)
            and self._clean_scene_text(scene.get("narration_segment", ""))
            and str(scene.get("narration_segment", "")).lower() not in {"intro branding", "outro branding"}
        ]
        if not spoken_scene_entries:
            return

        matched_spans: list[tuple[float, float]] = []
        search_index = 0
        for _, scene in spoken_scene_entries:
            scene_text = self._clean_scene_text(scene.get("narration_segment", ""))
            match_span = self._find_scene_segment_span(segments, scene_text, search_index)
            if match_span is None:
                return
            start_index, end_index = match_span
            matched_spans.append((segments[start_index].start_time, segments[end_index].end_time))
            search_index = end_index + 1

        first_spoken_scene_index = spoken_scene_entries[0][0]
        if first_spoken_scene_index > 0:
            first_spoken_start = matched_spans[0][0]
            for prior_scene in scenes[:first_spoken_scene_index]:
                if not isinstance(prior_scene, dict):
                    continue
                prior_scene["end_time"] = round(max(float(prior_scene.get("start_time") or 0.0), first_spoken_start), 3)

        for index, (_, scene) in enumerate(spoken_scene_entries):
            start, end = matched_spans[index]
            if index + 1 < len(matched_spans):
                next_start = matched_spans[index + 1][0]
                end = min(end, next_start)
            else:
                end = min(end, audio_duration)
            scene["start_time"] = round(start, 3)
            scene["end_time"] = round(max(start + 0.05, end), 3)

        scene_plan["total_duration"] = round(audio_duration, 3)
        save_json(scene_plan, self.scenes_dir / "scenes.json")

    def _find_scene_segment_span(
        self, segments: list[SubtitleSegment], scene_text: str, start_index: int
    ) -> Optional[tuple[int, int]]:
        target_tokens = self._match_tokens(scene_text)
        if not target_tokens:
            return None

        for index in range(start_index, len(segments)):
            best_end: Optional[int] = None
            best_prefix = 0
            max_window = min(len(segments), index + 12)
            for end_index in range(index, max_window):
                window = segments[index : end_index + 1]
                combined_tokens = self._match_tokens(" ".join(segment.text for segment in window))
                if not combined_tokens:
                    continue
                prefix_len = self._shared_prefix_len(combined_tokens, target_tokens)
                if prefix_len > best_prefix:
                    best_prefix = prefix_len
                    best_end = end_index
                if prefix_len == len(target_tokens):
                    return (index, end_index)
                if len(combined_tokens) >= len(target_tokens) and prefix_len < max(3, len(target_tokens) // 2):
                    break
            if best_end is not None and best_prefix >= min(5, len(target_tokens)):
                return (index, best_end)
        return None

    def _shared_prefix_len(self, left: list[str], right: list[str]) -> int:
        prefix_len = 0
        for a, b in zip(left, right, strict=False):
            if a != b:
                break
            prefix_len += 1
        return prefix_len

        scene_plan["total_duration"] = round(audio_duration, 3)
        save_json(scene_plan, self.scenes_dir / "scenes.json")

    def _find_scene_start_segment_index(
        self, segments: list[SubtitleSegment], scene_text: str, start_index: int
    ) -> Optional[int]:
        target_tokens = self._match_tokens(scene_text)
        if not target_tokens:
            return None

        max_window = min(6, len(segments) - start_index)
        for index in range(start_index, len(segments)):
            for window_size in range(1, max_window + 1):
                window = segments[index : index + window_size]
                if not window:
                    continue
                combined_tokens = self._match_tokens(" ".join(segment.text for segment in window))
                if not combined_tokens:
                    continue
                prefix_len = min(len(combined_tokens), len(target_tokens), 12)
                if prefix_len < 3:
                    continue
                if combined_tokens[:prefix_len] == target_tokens[:prefix_len]:
                    return index
        return None

    def _match_tokens(self, text: str) -> list[str]:
        normalized = self._match_key(text)
        return [token for token in normalized.split() if token]

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
        hours, minutes, rest = value.replace(".", ",").split(":")
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

    def _format_vtt(self, segments: list[SubtitleSegment]) -> str:
        cues = [
            TimedCue(
                start_time=segment.start_time,
                end_time=segment.end_time,
                text=segment.text,
                source="subtitle-stage",
            )
            for segment in segments
        ]
        return write_webvtt(cues)

    def _should_write_vtt_sidecar(self) -> bool:
        if not settings.tts_subtitles_enabled:
            return False
        requested_formats = {
            part.strip().lower()
            for part in settings.tts_subtitles_format.replace("+", ",").split(",")
            if part.strip()
        }
        return "vtt" in requested_formats or "webvtt" in requested_formats

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
