"""Utility functions for the pipeline."""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import settings


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists, create if needed."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_job_dir(job_id: str) -> Path:
    """Get the job directory for a specific job."""
    return ensure_dir(settings.jobs_dir / job_id)


def get_stage_dir(job_id: str, stage: str) -> Path:
    """Get the stage directory for a specific job."""
    return ensure_dir(get_job_dir(job_id) / stage)


def ensure_file_dir(path: Path) -> Path:
    """Ensure the parent directory of a file path exists."""
    return ensure_dir(path.parent)


def save_json(data: Any, path: Path) -> Path:
    """Save data as JSON file."""
    ensure_file_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def load_json(path: Path) -> Any:
    """Load data from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_job_id() -> str:
    """Generate a unique job ID."""
    return str(uuid.uuid4())


def format_duration(seconds: float) -> str:
    """Format duration in seconds to HH:MM:SS.ms."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def estimate_duration_from_words(word_count: int, words_per_minute: float = 150) -> float:
    """Estimate duration in seconds from word count."""
    return (word_count / words_per_minute) * 60


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    # Remove or replace invalid characters
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    # Replace multiple spaces with single space
    name = re.sub(r"\s+", " ", name)
    # Strip leading/trailing whitespace
    name = name.strip()[:100]  # Limit length
    return name or "untitled"


def split_text_into_chunks(
    text: str, max_words: int = 50, overlap_words: int = 5
) -> list[str]:
    """Split text into chunks for TTS processing."""
    words = text.split()
    chunks = []
    i = 0

    while i < len(words):
        chunk_words = words[i : i + max_words]
        chunks.append(" ".join(chunk_words))
        i += max_words - overlap_words

    return chunks


def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def generate_chapters_from_script(script: dict) -> list[dict]:
    """Generate YouTube chapters from a script."""
    chapters = []
    narration = script.get("narration", "")
    words = narration.split()

    # Simple chapter generation: split by roughly equal parts
    num_chapters = 5
    words_per_chapter = len(words) // num_chapters

    current_word = 0
    for i in range(num_chapters):
        start_time = (current_word / len(words)) * 100  # Assume 100 second video as baseline
        end_time = ((current_word + words_per_chapter) / len(words)) * 100

        # Generate chapter title based on position
        if i == 0:
            title = "Introduction"
        elif i == num_chapters - 1:
            title = "Conclusion & CTA"
        else:
            title = f"Sector {i}"

        chapters.append({
            "title": title,
            "timestamp": format_duration(start_time),
        })

        current_word += words_per_chapter

    return chapters


def create_directory_tree(path: Path, indent: str = "") -> str:
    """Create a text representation of directory tree."""
    lines = [f"{path.name}/"]

    if path.is_dir():
        for item in sorted(path.iterdir()):
            if item.is_dir():
                lines.append(f"{indent}  {create_directory_tree(item, indent + '  ')}")
            else:
                lines.append(f"{indent}  {item.name}")

    return "\n".join(lines)


def mock_response(data: Any) -> Any:
    """Return mock data for testing when mock_mode is enabled."""
    return data
