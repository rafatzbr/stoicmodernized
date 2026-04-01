"""Tests for configuration and settings."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import (
    ImageProvider,
    Settings,
    TTSProvider,
    VideoMode,
    YouTubePrivacy,
    settings,
)


class TestTTSProvider:
    """Tests for TTSProvider enum."""

    def test_local_value(self) -> None:
        """Should have correct local value."""
        assert TTSProvider.LOCAL.value == "local"

    def test_edge_value(self) -> None:
        """Should have correct edge value."""
        assert TTSProvider.EDGE.value == "edge"

    def test_elevenlabs_value(self) -> None:
        """Should have correct elevenlabs value."""
        assert TTSProvider.ELEVENLABS.value == "elevenlabs"


class TestImageProvider:
    """Tests for ImageProvider enum."""

    def test_sd_cli_value(self) -> None:
        """Should have correct sd_cli value."""
        assert ImageProvider.SD_CLI.value == "sd_cli"

    def test_dall_e_value(self) -> None:
        """Should have correct dall_e value."""
        assert ImageProvider.DALL_E.value == "dall_e"


class TestYouTubePrivacy:
    """Tests for YouTubePrivacy enum."""

    def test_public_value(self) -> None:
        """Should have correct public value."""
        assert YouTubePrivacy.PUBLIC.value == "public"

    def test_unlisted_value(self) -> None:
        """Should have correct unlisted value."""
        assert YouTubePrivacy.UNLISTED.value == "unlisted"

    def test_private_value(self) -> None:
        """Should have correct private value."""
        assert YouTubePrivacy.PRIVATE.value == "private"


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self) -> None:
        """Should have correct default values."""
        assert settings.channel_name == "Stoic Modernized"
        assert settings.video_width == 1920
        assert settings.video_height == 1080
        assert settings.short_video_width == 1080
        assert settings.short_video_height == 1920
        assert settings.default_video_mode == VideoMode.SHORT
        assert settings.video_fps == 30
        assert settings.tts_provider == TTSProvider.LOCAL
        assert settings.tts_voice == "en-US-GuyNeural"
        assert settings.tts_speed == 1.0
        assert settings.sd_image_width == 544
        assert settings.sd_image_height == 960
        assert settings.youtube_privacy_status == YouTubePrivacy.UNLISTED
        assert settings.mock_mode is False

    def test_db_path_is_path_object(self) -> None:
        """Should create db_path as Path object."""
        assert isinstance(settings.db_path, Path)

    def test_jobs_dir_is_path_object(self) -> None:
        """Should create jobs_dir as Path object."""
        assert isinstance(settings.jobs_dir, Path)

    def test_output_dir_is_path_object(self) -> None:
        """Should create output_dir as Path object."""
        assert isinstance(settings.output_dir, Path)

    def test_db_property_format(self) -> None:
        """Should format database connection string correctly."""
        db_url = settings.db

        assert db_url.startswith("sqlite:///")
        assert str(settings.db_path) in db_url

    def test_environment_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should allow environment variable overrides."""
        monkeypatch.setenv("MOCK_MODE", "true")
        monkeypatch.setenv("YOUTUBE_PRIVACY_STATUS", "public")
        monkeypatch.setenv("CHANNEL_NAME", "Custom Channel")

        # Create new settings instance with fresh environment
        from src.config import Settings as TestSettings

        test_settings = TestSettings()

        assert test_settings.mock_mode is True
        assert test_settings.youtube_privacy_status == YouTubePrivacy.PUBLIC
        assert test_settings.channel_name == "Custom Channel"

    def test_invalid_privacy_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should raise validation error for invalid privacy status."""
        monkeypatch.setenv("YOUTUBE_PRIVACY_STATUS", "invalid_status")

        with pytest.raises(ValidationError):
            Settings()

    def test_invalid_tts_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should raise validation error for invalid TTS provider."""
        monkeypatch.setenv("TTS_PROVIDER", "invalid_provider")

        with pytest.raises(ValidationError):
            Settings()

    def test_video_settings_1080p(self) -> None:
        """Should have 1080p default resolution."""
        assert settings.video_width == 1920
        assert settings.video_height == 1080

    def test_image_settings_vertical(self) -> None:
        """Should have vertical image dimensions for YouTube."""
        assert settings.sd_image_width == 544
        assert settings.sd_image_height == 960
        assert settings.sd_image_height > settings.sd_image_width

    def test_background_music_volume_range(self) -> None:
        """Should have valid background music volume."""
        assert 0.0 <= settings.background_music_volume <= 1.0
        assert settings.background_music_volume == 0.15
