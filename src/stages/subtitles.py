"""Subtitle generation stage module."""

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
        segments = self._parse_narration_to_segments(narration)
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

    def _parse_narration_to_segments(self, narration: str) -> list[SubtitleSegment]:
        segments = []
        lines = narration.split("\n")
        current_time = 0.0

        for line in lines:
            if line.startswith("[") and "]" in line:
                time_str = line[1:line.index("]")]
                if "-" in time_str:
                    start_str, _ = time_str.split("-")
                    parts = start_str.split(":")
                    if len(parts) == 2:
                        minutes, seconds = map(float, parts)
                        current_time = minutes * 60 + seconds
                continue

            clean_line = line.strip()
            if not clean_line:
                continue

            words = clean_line.split()
            duration = max(1.4, len(words) / 2.6)
            end_time = current_time + duration

            segments.append(
                SubtitleSegment(
                    start_time=round(current_time, 2),
                    end_time=round(end_time, 2),
                    text=clean_line,
                )
            )
            current_time = end_time

        return segments

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
