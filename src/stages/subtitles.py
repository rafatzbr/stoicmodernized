"""Subtitle generation stage module."""

import re
from pathlib import Path
from typing import Optional

from src.config import settings
from src.models import SubtitleSegment, SubtitleResult
from src.utils import save_json


class SubtitleStage:
    """Handles subtitle generation."""

    def __init__(self, job_id: str, mock: bool = False):
        """Initialize subtitle stage.

        Args:
            job_id: Unique job identifier
            mock: If True, use mock data
        """
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.job_dir = settings.jobs_dir / job_id
        self.subtitles_dir = self.job_dir / "subtitles"

    async def run(self, script_data: dict, audio_path: Optional[str] = None) -> SubtitleResult:
        """Generate subtitles from script.

        Args:
            script_data: Script data with narration
            audio_path: Optional path to audio file for real timing

        Returns:
            SubtitleResult with SRT content and timing data
        """
        self.subtitles_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._mock_generate(script_data)
        else:
            return await self._real_generate(script_data, audio_path)

    async def _mock_generate(self, script_data: dict) -> SubtitleResult:
        """Generate mock subtitles from script narration."""
        narration = script_data.get("narration", "")
        segments = self._parse_narration_to_segments(narration)

        srt_content = self._format_srt(segments)

        srt_path = self.subtitles_dir / "subtitles.srt"
        json_path = self.subtitles_dir / "subtitles.json"

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        save_json({"segments": segments}, json_path)

        return SubtitleResult(
            srt_content=srt_content,
            segments=segments,
            srt_path=str(srt_path),
            json_path=str(json_path),
        )

    async def _real_generate(
        self, script_data: dict, audio_path: Optional[str] = None
    ) -> SubtitleResult:
        """Generate real subtitles with audio timing.

        TODO: Implement real subtitle generation using:
        - Whisper for speech-to-text
        - VAD (Voice Activity Detection)
        - Word-level timing from audio
        """
        # Fall back to mock implementation
        return await self._mock_generate(script_data)

    def _parse_narration_to_segments(self, narration: str) -> list[SubtitleSegment]:
        """Parse narration text into subtitle segments.

        Args:
            narration: Full narration text with timestamp markers

        Returns:
            List of SubtitleSegment objects
        """
        segments = []
        lines = narration.split("\n")

        current_time = 0.0
        segment_num = 0

        for line in lines:
            # Parse timestamp markers
            if line.startswith("[") and "]" in line:
                time_str = line[1:line.index("]")]
                if "-" in time_str:
                    start_str, _ = time_str.split("-")
                    parts = start_str.split(":")
                    if len(parts) == 2:
                        minutes, seconds = map(float, parts)
                        current_time = minutes * 60 + seconds

            # Parse narration text
            if line and not line.startswith("[") and line.strip():
                words = line.strip().split()
                duration = len(words) / 2.5  # ~2.5 words per second
                end_time = current_time + duration

                segments.append(
                    SubtitleSegment(
                        start_time=round(current_time, 2),
                        end_time=round(end_time, 2),
                        text=line.strip(),
                    )
                )

                current_time = end_time
                segment_num += 1

        return segments

    def _format_srt(self, segments: list[SubtitleSegment]) -> str:
        """Format segments as SRT subtitle file.

        Args:
            segments: List of subtitle segments

        Returns:
            SRT formatted string
        """
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
        """Format time as SRT timestamp (HH:MM:SS,ms).

        Args:
            seconds: Time in seconds

        Returns:
            SRT formatted timestamp string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        ms = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

    def save_subtitles(self, result: SubtitleResult) -> None:
        """Save subtitle files.

        Args:
            result: SubtitleResult to save
        """
        # SRT file already saved in _mock_generate
        pass

    def load_subtitles(self) -> Optional[SubtitleResult]:
        """Load subtitles from JSON.

        Returns:
            SubtitleResult if found, None otherwise
        """
        json_path = self.subtitles_dir / "subtitles.json"
        if not json_path.exists():
            return None

        data = save_json.__globals__["load_json"](json_path)

        return SubtitleResult(
            srt_content="",
            segments=[SubtitleSegment(**s) for s in data.get("segments", [])],
            srt_path="",
            json_path=str(json_path),
        )
