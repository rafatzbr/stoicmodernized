"""Narration preparation stage - optimizes script for natural TTS delivery."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.config import Channel, settings
from src.stages.pronunciation_dict import PronunciationDictionary
from src.utils import load_json, save_json


@dataclass
class PreparedLine:
    """A single prepared narration line."""
    line: str
    delivery_note: str = "normal"  # normal | slight_emphasis | slower | short_pause_after | longer_pause_after


@dataclass
class PronunciationNote:
    """Pronunciation guidance for TTS."""
    term: str
    spoken_as: str
    reason: str


@dataclass
class NarrationPreparationResult:
    """Result of narration preparation."""
    narration_style: str
    target_duration_seconds: float
    prepared_script: list[PreparedLine]
    pronunciation_notes: list[PronunciationNote]
    tts_warnings: list[str]


class NarrationPreparationStage:
    """Prepares script for natural TTS delivery."""

    def __init__(self, job_id: str, mock: bool = False, channel: Channel = settings.default_channel):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.channel = channel
        self.job_dir = settings.jobs_dir / job_id
        self.script_dir = self.job_dir / "script"
    def __init__(self, job_id: str, mock: bool = False, channel: Channel = settings.default_channel):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.channel = channel
        self.job_dir = settings.jobs_dir / job_id
        self.script_dir = self.job_dir / "script"
        self.pronunciation_dict = PronunciationDictionary()

    async def run(self, script_data: dict) -> NarrationPreparationResult:
        """Prepare narration script for TTS."""
        narration = script_data.get("narration", "")
        
        if self.mock:
            return self._mock_preparation(narration)

        # Parse into lines
        lines = self._parse_narration_lines(narration)
        
        # First pass: substitute pronunciations in full narration
        optimized_narration, dict_notes = self._substitute_pronunciations(narration)
        
        # Parse optimized narration into lines
        optimized_lines = self._parse_narration_lines(optimized_narration)
        
        # Optimize each line for TTS
        prepared_lines = []
        pronunciation_notes = list(dict_notes)  # Start with pronunciation dict notes
        tts_warnings = []

        for line in optimized_lines:
            prepared_line, pron_notes, warnings = self._prepare_line(line)
            prepared_lines.append(prepared_line)
            pronunciation_notes.extend(pron_notes)
            tts_warnings.extend(warnings)

        # Calculate estimated duration
        target_duration = self._estimate_duration(prepared_lines)

        return NarrationPreparationResult(
            narration_style="calm tech commentator",
            target_duration_seconds=target_duration,
            prepared_script=prepared_lines,
            pronunciation_notes=pronunciation_notes,
            tts_warnings=tts_warnings,
        )

    def _parse_narration_lines(self, narration: str) -> list[str]:
        """Parse narration into individual lines."""
        lines = []
        
        for line in narration.split("\n"):
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Skip section headers
            if line.startswith("Section "):
                continue
            
            # Skip timed block markers like [0:00-0:08]
            if re.match(r"^\[\d+:\d+-\d+:\d+\]", line):
                continue
            
            # Skip lines that are just section titles (all caps)
            if line.isupper() and len(line) > 5 and "Section" not in line:
                # Check if it's a section title vs actual narration
                if line in ["TITLE SCREEN", "TITLE ANNOUNCEMENT"]:
                    continue
                # Otherwise keep it (could be a headline or title)
            
            lines.append(line)
        
        return lines

    def _prepare_line(self, line: str) -> tuple[PreparedLine, list[PronunciationNote], list[str]]:
        """Prepare a single line for TTS."""
        pronunciation_notes = []
        tts_warnings = []
        delivery_note = "normal"

        # Check for extremely long sentences
        words = line.split()
        if len(words) > 25:
            delivery_note = "slower"
            tts_warnings.append(f"Long sentence ({len(words)} words) - may need slower delivery")

        # Check for numbers that might be read incorrectly
        number_matches = re.findall(r"\b\d{4}\b", line)
        for num in number_matches:
            pronunciation_notes.append(PronunciationNote(
                term=num,
                spoken_as=num,  # TTS will handle 4-digit years correctly
                reason="Year format"
            ))

        # Check for acronyms and terms that need pronunciation guidance (fallback for line-level)
        # The full pronunciation dictionary substitution happens at the narration level above

        # Check for pacing issues
        if "..." in line:
            delivery_note = "short_pause_after"
        elif line.endswith(".") and len(words) > 15:
            delivery_note = "short_pause_after"
        elif line.endswith("!") or line.endswith("?"):
            delivery_note = "slight_emphasis"

        # Add longer pause after title announcements
        if "today" in line.lower() and "five" in line.lower() and "stories" in line.lower():
            delivery_note = "short_pause_after"

        return PreparedLine(line=line, delivery_note=delivery_note), pronunciation_notes, tts_warnings

    def _substitute_pronunciations(self, text: str) -> tuple[str, list[PronunciationNote]]:
        """Substitute pronunciations in text for safer TTS reading."""
        notes = []
        result = text
        
        # Find all terms that need pronunciation guidance
        issues = self.pronunciation_dict.find_pronunciation_issues(text)
        
        for issue in issues:
            term = issue["term"]
            spoken = issue["spoken_as"]
            reason = issue["reason"]
            
            # Add pronunciation note
            notes.append(PronunciationNote(
                term=term,
                spoken_as=spoken,
                reason=reason
            ))
            
            # Substitute in text if configured
            if self.pronunciation_dict.should_replace(term):
                pattern = r'\b' + re.escape(term) + r'\b'
                result = re.sub(pattern, spoken, result, flags=re.IGNORECASE)
        
        return result, notes

    def _estimate_duration(self, prepared_lines: list[PreparedLine]) -> float:
        """Estimate total duration based on line count and delivery notes."""
        base_rate = 2.2  # words per second
        total_words = 0
        duration = 0.0

        for line in prepared_lines:
            words = len(line.line.split())
            total_words += words

            # Adjust for delivery notes
            if line.delivery_note == "slower":
                duration += words / (base_rate * 0.85)
            elif line.delivery_note == "short_pause_after":
                duration += words / base_rate + 0.3
            elif line.delivery_note == "longer_pause_after":
                duration += words / base_rate + 0.6
            else:
                duration += words / base_rate

        # Add title screen and outro buffers for Stoic Modernized
        duration += 5.0  # Title screen
        duration += 2.0  # Outro CTA

        return round(duration, 1)

    def _mock_preparation(self, narration: str) -> NarrationPreparationResult:
        """Mock preparation for testing."""
        lines = self._parse_narration_lines(narration)
        prepared_lines = [PreparedLine(line=line) for line in lines]
        
        return NarrationPreparationResult(
            narration_style="calm tech commentator",
            target_duration_seconds=54.0,
            prepared_script=prepared_lines,
            pronunciation_notes=[],
            tts_warnings=[],
        )

    def save_preparation(self, result: NarrationPreparationResult) -> Path:
        """Save prepared narration to file."""
        self.script_dir.mkdir(parents=True, exist_ok=True)

        output = {
            "narration_style": result.narration_style,
            "target_duration_seconds": result.target_duration_seconds,
            "prepared_script": [
                {"line": line.line, "delivery_note": line.delivery_note}
                for line in result.prepared_script
            ],
            "pronunciation_notes": [
                {"term": note.term, "spoken_as": note.spoken_as, "reason": note.reason}
                for note in result.pronunciation_notes
            ],
            "tts_warnings": result.tts_warnings,
        }

        path = self.script_dir / "narration_prep.json"
        save_json(output, path)
        return path
