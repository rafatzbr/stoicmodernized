"""Test fixtures and configuration."""

import os
from pathlib import Path

import pytest
from src.config import Settings


@pytest.fixture(autouse=True)
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure mock mode is enabled for all tests."""
    monkeypatch.setenv("MOCK_MODE", "true")


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    """Create a test settings instance with tmp directory."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))

    from src.config import Settings as TestSettings

    return TestSettings()


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for tests."""
    return tmp_path


@pytest.fixture
def sample_research_data() -> dict:
    """Sample research data for testing."""
    return {
        "topic": "workplace stress",
        "title": "Workplace Stress: A Stoic Perspective",
        "sources": [
            {
                "title": "Meditations - Marcus Aurelius",
                "url": "https://example.com/meditations",
                "note": "Primary Stoic source",
                "relevance": 0.95,
                "source": "book",
            },
        ],
        "key_insights": [
            "Stoicism teaches control of reactions",
            "Ancient wisdom applies to modern stress",
        ],
        "workplace_applications": [
            "Morning preparation before meetings",
            "View from above technique",
        ],
    }


@pytest.fixture
def sample_script_data() -> dict:
    """Sample script data for testing."""
    return {
        "title": "Workplace Stress: A Stoic Perspective",
        "topic": "workplace stress",
        "hook": "What if 2000 years of wisdom could help you handle stress?",
        "narration": "[0:00-0:30] Introduction\n\nWelcome to Stoic Modernized.",
        "chapters": [
            {"title": "Introduction", "timestamp": 0.0},
            {"title": "The Problem", "timestamp": 30.0},
            {"title": "Conclusion", "timestamp": 450.0},
        ],
        "cta": "Subscribe for more",
        "research_sources": [],
    }


@pytest.fixture
def sample_scene_plan() -> dict:
    """Sample scene plan for testing."""
    return {
        "job_id": "test-job-123",
        "title": "Workplace Stress: A Stoic Perspective",
        "total_scenes": 3,
        "estimated_duration": 540.0,
        "scenes": [
            {
                "scene_number": 0,
                "start_time": 0.0,
                "end_time": 3.0,
                "narration_segment": "Intro",
                "visual_prompt": "Stoic Modernized intro",
                "text_overlay": "Stoic Modernized",
                "animation_style": "fade",
            },
            {
                "scene_number": 1,
                "start_time": 3.0,
                "end_time": 100.0,
                "narration_segment": "Welcome to Stoic Modernized.",
                "visual_prompt": "Roman column silhouette",
                "text_overlay": "Control",
                "animation_style": "zoom",
            },
            {
                "scene_number": 2,
                "start_time": 100.0,
                "end_time": 540.0,
                "narration_segment": "Conclusion",
                "visual_prompt": "Philosopher bust",
                "text_overlay": "Freedom",
                "animation_style": "zoom",
            },
        ],
    }


@pytest.fixture
def sample_metadata() -> dict:
    """Sample YouTube metadata for testing."""
    return {
        "title": "Workplace Stress: A Stoic Perspective | Stoic Modernized",
        "description": "In this video, we explore workplace stress...",
        "tags": ["stoicism", "workplace", "stress", "productivity"],
        "chapters": [
            {"title": "Introduction", "timestamp": 0},
            {"title": "The Problem", "timestamp": 30},
            {"title": "Conclusion", "timestamp": 450},
        ],
        "privacy_status": "unlisted",
    }
