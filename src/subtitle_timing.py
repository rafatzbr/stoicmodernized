"""Provider-neutral subtitle timing helpers for video narration workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TimedWord:
    """A word or token with provider/alignment timing metadata."""

    text: str
    start_time: float
    end_time: float
    source: str = "unknown"
    confidence: Optional[float] = None


@dataclass(frozen=True)
class TimedCue:
    """A readable subtitle cue derived from timed words or heuristics."""

    start_time: float
    end_time: float
    text: str
    source: str = "unknown"
    words: list[TimedWord] = field(default_factory=list)


_SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]*$")
_PHRASE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE = re.compile(r"\s+")
_VTT_TIMING_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}[\.,]\d{3})\s+-->\s+"
    r"(?P<end>\d{2}:\d{2}:\d{2}[\.,]\d{3})"
)


def group_words_into_readable_cues(
    words: list[TimedWord],
    *,
    max_words: int = 8,
    max_duration: float = 3.0,
) -> list[TimedCue]:
    """Group provider word timings into readable phrase-level cues."""

    ordered_words = [word for word in words if word.text.strip() and word.end_time > word.start_time]
    if not ordered_words:
        return []

    cues: list[TimedCue] = []
    current: list[TimedWord] = []

    for word in ordered_words:
        if current and word.start_time < current[-1].end_time:
            word = TimedWord(
                text=word.text,
                start_time=current[-1].end_time,
                end_time=max(word.end_time, current[-1].end_time + 0.001),
                source=word.source,
                confidence=word.confidence,
            )
        current.append(word)
        duration = current[-1].end_time - current[0].start_time
        should_close = (
            len(current) >= max_words
            or duration >= max_duration
            or bool(_SENTENCE_END_RE.search(word.text.strip()))
        )
        if should_close:
            cues.append(_cue_from_words(current))
            current = []

    if current:
        cues.append(_cue_from_words(current))

    return cues


def make_heuristic_cues(
    text: str,
    *,
    duration: float,
    source: str = "heuristic",
) -> list[TimedCue]:
    """Create approximate readable cues from transcript text and audio duration."""

    phrases = _split_text_into_readable_phrases(text)
    if not phrases or duration <= 0:
        return []

    total_weight = sum(max(1, len(phrase.split())) for phrase in phrases)
    current_time = 0.0
    cues: list[TimedCue] = []

    for index, phrase in enumerate(phrases):
        if index == len(phrases) - 1:
            end_time = duration
        else:
            weight = max(1, len(phrase.split()))
            end_time = min(duration, current_time + duration * (weight / total_weight))
        cues.append(
            TimedCue(
                start_time=round(current_time, 3),
                end_time=round(max(current_time, end_time), 3),
                text=phrase,
                source=source,
            )
        )
        current_time = end_time

    return cues


def write_webvtt(cues: list[TimedCue]) -> str:
    """Render cues as deterministic WebVTT text."""

    valid_cues = _validate_and_sort_cues(cues)
    lines = ["WEBVTT", ""]
    for index, cue in enumerate(valid_cues):
        lines.append(f"{_format_vtt_timestamp(cue.start_time)} --> {_format_vtt_timestamp(cue.end_time)}")
        lines.append(_clean_cue_text(cue.text))
        if index != len(valid_cues) - 1:
            lines.append("")
    return "\n".join(lines) + "\n"


def parse_webvtt_cues(text: str, *, source: str = "unknown") -> list[TimedCue]:
    """Parse WebVTT/SRT-style cue text into normalized timing cues."""

    cues: list[TimedCue] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        timing = _VTT_TIMING_RE.search(line)
        if not timing:
            index += 1
            continue

        cue_lines: list[str] = []
        index += 1
        while index < len(lines) and lines[index].strip():
            cue_lines.append(lines[index].strip())
            index += 1

        cue_text = _clean_cue_text(" ".join(cue_lines))
        if cue_text:
            cues.append(
                TimedCue(
                    start_time=round(_parse_vtt_timestamp(timing.group("start")), 3),
                    end_time=round(_parse_vtt_timestamp(timing.group("end")), 3),
                    text=cue_text,
                    source=source,
                )
            )
        index += 1

    return _validate_and_sort_cues(cues)


def _cue_from_words(words: list[TimedWord]) -> TimedCue:
    text = _clean_cue_text(" ".join(word.text.strip() for word in words))
    source = words[0].source if words else "unknown"
    return TimedCue(
        start_time=round(words[0].start_time, 3),
        end_time=round(words[-1].end_time, 3),
        text=text,
        source=source,
        words=list(words),
    )


def _split_text_into_readable_phrases(text: str) -> list[str]:
    clean = _clean_cue_text(text)
    if not clean:
        return []

    phrases: list[str] = []
    for sentence in _PHRASE_SPLIT_RE.split(clean):
        words = sentence.split()
        if len(words) <= 8:
            phrases.append(sentence.strip())
            continue
        current: list[str] = []
        for word in words:
            current.append(word)
            if len(current) >= 6:
                phrases.append(" ".join(current).strip())
                current = []
        if current:
            phrases.append(" ".join(current).strip())
    return [phrase for phrase in phrases if phrase]


def _validate_and_sort_cues(cues: list[TimedCue]) -> list[TimedCue]:
    sorted_cues = sorted(cues, key=lambda cue: (cue.start_time, cue.end_time))
    valid: list[TimedCue] = []
    previous_end = 0.0
    for cue in sorted_cues:
        text = _clean_cue_text(cue.text)
        if not text or cue.end_time <= cue.start_time:
            continue
        start = max(0.0, cue.start_time, previous_end)
        end = max(start + 0.001, cue.end_time)
        normalized = TimedCue(
            start_time=round(start, 3),
            end_time=round(end, 3),
            text=text,
            source=cue.source,
            words=cue.words,
        )
        valid.append(normalized)
        previous_end = normalized.end_time
    return valid


def _format_vtt_timestamp(seconds: float) -> str:
    millis_total = int(round(max(0.0, seconds) * 1000))
    hours, remainder = divmod(millis_total, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{millis:03d}"


def _parse_vtt_timestamp(value: str) -> float:
    hours, minutes, rest = value.replace(",", ".").split(":")
    seconds, millis = rest.split(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def _clean_cue_text(text: str) -> str:
    clean = text.replace("\r", " ").replace("\n", " ")
    clean = re.sub(r"<\d{2}:\d{2}:\d{2}[\.,]\d{3}>", " ", clean)
    clean = re.sub(r"</?[^>]+>", " ", clean)
    clean = _WHITESPACE_RE.sub(" ", clean).strip()
    clean = re.sub(r"\s+([,.;:!?])", r"\1", clean)
    return clean
