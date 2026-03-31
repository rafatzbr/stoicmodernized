"""Tests for utility functions."""

import json
import tempfile
from pathlib import Path

import pytest

from src.utils import (
    ensure_dir,
    ensure_file_dir,
    format_duration,
    generate_job_id,
    load_json,
    save_json,
    sanitize_filename,
    split_text_into_chunks,
    word_count,
)


class TestEnsureDir:
    """Tests for ensure_dir function."""

    def test_creates_new_directory(self, tmp_path: Path) -> None:
        """Should create a new directory."""
        new_dir = tmp_path / "new_dir"
        result = ensure_dir(new_dir)

        assert result.exists()
        assert result.is_dir()
        assert result == new_dir

    def test_does_not_fail_on_existing_directory(self, tmp_path: Path) -> None:
        """Should not fail if directory already exists."""
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()

        result = ensure_dir(existing_dir)

        assert result.exists()
        assert result.is_dir()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if they don't exist."""
        new_dir = tmp_path / "parent" / "child" / "grandchild"

        result = ensure_dir(new_dir)

        assert result.exists()
        assert result.is_dir()


class TestEnsureFileDir:
    """Tests for ensure_file_dir function."""

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        """Should create parent directory for a file."""
        file_path = tmp_path / "parent" / "child" / "file.txt"

        result = ensure_file_dir(file_path)

        assert result.exists()
        assert result.is_dir()


class TestSaveJson:
    """Tests for save_json function."""

    def test_saves_json_correctly(self, tmp_path: Path) -> None:
        """Should save data as properly formatted JSON."""
        data = {"name": "test", "value": 42, "items": [1, 2, 3]}
        file_path = tmp_path / "data.json"

        result = save_json(data, file_path)

        assert result == file_path
        assert file_path.exists()

        with open(file_path) as f:
            loaded = json.load(f)

        assert loaded == data

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Should create parent directories if needed."""
        data = {"key": "value"}
        file_path = tmp_path / "nonexistent" / "dir" / "data.json"

        result = save_json(data, file_path)

        assert result.exists()


class TestLoadJson:
    """Tests for load_json function."""

    def test_loads_json_correctly(self, tmp_path: Path) -> None:
        """Should load data from JSON file."""
        data = {"name": "test", "value": 42}
        file_path = tmp_path / "data.json"
        save_json(data, file_path)

        result = load_json(file_path)

        assert result == data

    def test_handles_nested_structures(self, tmp_path: Path) -> None:
        """Should handle nested JSON structures."""
        data = {
            "outer": {
                "inner": {
                    "value": [1, 2, 3],
                },
            },
        }
        file_path = tmp_path / "nested.json"
        save_json(data, file_path)

        result = load_json(file_path)

        assert result == data


class TestGenerateJobId:
    """Tests for generate_job_id function."""

    def test_generates_unique_ids(self) -> None:
        """Should generate unique job IDs."""
        ids = [generate_job_id() for _ in range(100)]

        assert len(ids) == len(set(ids))

    def test_generates_valid_uuid_format(self) -> None:
        """Should generate valid UUID format."""
        job_id = generate_job_id()

        # UUID format: 8-4-4-4-12
        parts = job_id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12


class TestFormatDuration:
    """Tests for format_duration function."""

    def test_formats_zero_seconds(self) -> None:
        """Should format 0 seconds correctly."""
        result = format_duration(0.0)
        assert result == "00:00:00.000"

    def test_formats_one_minute(self) -> None:
        """Should format 1 minute correctly."""
        result = format_duration(60.0)
        assert result == "00:01:00.000"

    def test_formats_one_hour(self) -> None:
        """Should format 1 hour correctly."""
        result = format_duration(3600.0)
        assert result == "01:00:00.000"

    def test_formats_with_milliseconds(self) -> None:
        """Should format with milliseconds."""
        result = format_duration(65.5)
        assert result == "00:01:05.500"


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_removes_invalid_characters(self) -> None:
        """Should remove characters invalid for filenames."""
        filename = "test:<file|name>.txt"
        result = sanitize_filename(filename)

        assert ":" not in result
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result

    def test_replaces_multiple_spaces(self) -> None:
        """Should replace multiple spaces with single space."""
        filename = "test    multiple    spaces.txt"
        result = sanitize_filename(filename)

        assert "  " not in result
        assert "multiple" in result

    def test_limits_length(self) -> None:
        """Should limit filename length."""
        long_name = "a" * 200 + ".txt"
        result = sanitize_filename(long_name)

        assert len(result) <= 103  # 100 + .txt

    def test_strips_whitespace(self) -> None:
        """Should strip leading/trailing whitespace."""
        filename = "  test file  "
        result = sanitize_filename(filename)

        assert result == "test file"

    def test_handles_empty_string(self) -> None:
        """Should handle empty string."""
        result = sanitize_filename("")

        assert result == "untitled"


class TestSplitTextIntoChunks:
    """Tests for split_text_into_chunks function."""

    def test_splits_correctly(self) -> None:
        """Should split text into chunks with overlap."""
        text = " ".join([f"word{i}" for i in range(20)])
        chunks = split_text_into_chunks(text, max_words=5, overlap_words=2)

        # Should create chunks with 5 words each, 2-word overlap
        assert len(chunks) > 1

    def test_handles_short_text(self) -> None:
        """Should handle text shorter than max_words."""
        text = "short text"
        chunks = split_text_into_chunks(text, max_words=10)

        assert len(chunks) == 1
        assert chunks[0] == text


class TestWordCount:
    """Tests for word_count function."""

    def test_counts_words_correctly(self) -> None:
        """Should count words correctly."""
        assert word_count("hello world") == 2
        assert word_count("one") == 1
        assert word_count("") == 0
        assert word_count("  multiple   spaces  ") == 2
