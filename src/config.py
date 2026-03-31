"""Configuration and settings for the stoic-modernized pipeline."""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TTSProvider(str, Enum):
    """Supported TTS providers."""

    LOCAL = "local"
    EDGE = "edge"
    ELEVENLABS = "elevenlabs"


class ImageProvider(str, Enum):
    """Supported image generation providers."""

    SD_CLI = "sd_cli"
    DALL_E = "dall_e"


class YouTubePrivacy(str, Enum):
    """YouTube privacy settings."""

    PUBLIC = "public"
    UNLISTED = "unlisted"
    PRIVATE = "private"


class Settings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    # Project paths
    project_root: Path = Path(__file__).parent.parent
    output_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "output")
    jobs_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "output" / "jobs")

    # Database
    db_path: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "stoic.db")

    # Brand settings
    channel_name: str = "Stoic Modernized"
    channel_voice: str = "calm, practical, concise, modern, not preachy, not academic"

    # Video settings
    video_width: int = 1920
    video_height: int = 1080  # 1080p output
    video_fps: int = 30
    background_music_volume: float = 0.15  # 15% volume for background music

    # TTS settings
    tts_provider: TTSProvider = TTSProvider.LOCAL
    tts_voice: str = "en-US-GuyNeural"
    tts_speed: float = 1.0
    tts_api_key: Optional[str] = None  # For ElevenLabs

    # Image generation settings (sd-cli)
    sd_cli_path: str = "/home/rafatz/dev/stable-diffusion.cpp/build/bin/sd-cli"
    sd_model_path: str = "/data/sd-models/sd3.5_large.safetensors"
    sd_clip_l_path: str = "/data/sd-models/clip_l.safetensors"
    sd_clip_g_path: str = "/data/sd-models/clip_g.safetensors"
    sd_t5xxl_path: str = "/data/sd-models/t5xxl_fp16.safetensors"
    sd_image_width: int = 1080
    sd_image_height: int = 1920  # Vertical for YouTube
    sd_cfg_scale: float = 7.0
    sd_sampling_method: str = "euler"

    # YouTube settings
    youtube_api_key: Optional[str] = None
    youtube_privacy_status: YouTubePrivacy = YouTubePrivacy.UNLISTED
    youtube_schedule_datetime: Optional[str] = None

    # Mock mode - useful when API keys are missing
    mock_mode: bool = False

    @property
    def db(self) -> str:
        """Database connection string."""
        return f"sqlite:///{self.db_path}"


# Global settings instance
settings = Settings()
