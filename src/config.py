"""Configuration and settings for the stoic-modernized pipeline."""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TTSProvider(str, Enum):
    """Supported TTS providers."""

    LOCAL = "local"
    EDGE = "edge"
    ELEVENLABS = "elevenlabs"
    VOXCPM = "voxcpm"


class ImageProvider(str, Enum):
    """Supported image generation providers."""

    SD_CLI = "sd_cli"
    SD_SERVER = "sd_server"
    DALL_E = "dall_e"


class YouTubePrivacy(str, Enum):
    """YouTube privacy settings."""

    PUBLIC = "public"
    UNLISTED = "unlisted"
    PRIVATE = "private"


class VideoMode(str, Enum):
    """Supported output video modes."""

    SHORT = "short"
    LONG = "long"


class Settings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    project_root: Path = Path(__file__).parent.parent
    output_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "output")
    jobs_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "output" / "jobs")

    db_path: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "stoic.db")

    channel_name: str = "Stoic Modernized"
    channel_voice: str = "calm, practical, concise, modern, not preachy, not academic"

    default_video_mode: VideoMode = VideoMode.SHORT
    video_width: int = 1920
    video_height: int = 1080
    short_video_width: int = 1080
    short_video_height: int = 1920
    short_max_duration_seconds: int = 60
    long_max_duration_seconds: int = 900
    video_fps: int = 30
    background_music_volume: float = 0.15

    tts_provider: TTSProvider = TTSProvider.LOCAL
    tts_voice: str = Field(default="en-US-GuyNeural", validation_alias=AliasChoices("TTS_VOICE", "TS_VOICE"))
    tts_speed: float = 1.0
    tts_api_key: Optional[str] = None

    subtitle_asr_enabled: bool = True
    subtitle_asr_model: str = "openai/whisper-tiny.en"
    subtitle_asr_language: str = "english"
    subtitle_asr_chunk_length_s: int = 20

    sd_cli_path: str = "/home/rafatz/dev/stable-diffusion.cpp/build/bin/sd-cli"
    sd_model_path: str = "/data/sd-models/sd3.5_large.safetensors"
    sd_clip_l_path: str = "/data/sd-models/clip_l.safetensors"
    sd_clip_g_path: str = "/data/sd-models/clip_g.safetensors"
    sd_t5xxl_path: str = "/data/sd-models/t5xxl_fp16.safetensors"
    sd_image_width: int = 544
    sd_image_height: int = 960
    sd_cfg_scale: float = 3.8  # Rafael 2026-04-05: Lower for more natural results (3.5-4.0 range)
    sd_steps: int = 20  # Rafael 2026-04-05: Start with 40, compare with 30-36
    sd_sampling_method: str = "euler"
    sd_negative_prompt: str = "blurry, low quality, deformed, extra people in foreground, cluttered desk, text, logo, watermark, overexposed, bad hands, extra fingers, missing fingers, duplicate objects, malformed laptop, distorted pen, plastic skin, uncanny smile, centered headshot, stiff stock photo pose, oversmoothed skin, multiple computers"
    force_placeholder_images: bool = False

    # SD Server (local stable diffusion web UI or ComfyUI)
    sd_server_url: str = "http://localhost:1234"
    sd_server_api_path: str = "/sdapi/v1/txt2img"
    sd_server_timeout_seconds: float = 300.0

    youtube_api_key: Optional[str] = None
    youtube_credentials_path: Optional[str] = None
    youtube_privacy_status: YouTubePrivacy = YouTubePrivacy.UNLISTED
    youtube_schedule_datetime: Optional[str] = None

    local_llm_base_url: str = "http://localhost:8080/v1/chat/completions"
    local_llm_model: str = "local"
    local_llm_timeout_seconds: float = 120.0
    local_llm_max_tokens: int = 32

    local_script_model: Optional[str] = None
    local_script_max_tokens: int = 1800
    local_script_temperature: float = 0.7
    local_script_min_section_words: int = 8

    local_image_prompt_model: Optional[str] = None
    local_image_prompt_max_tokens: int = 220
    local_image_prompt_temperature: float = 0.4

    local_scene_model: Optional[str] = None
    local_scene_max_tokens: int = 1400
    local_scene_temperature: float = 0.3

    watermark_logo_path: Path = Path('/home/rafatz/media/logo_transparent.png')
    watermark_scale_width: int = 240
    watermark_padding: int = 36

    mock_mode: bool = False

    @property
    def db(self) -> str:
        """Database connection string."""
        return f"sqlite:///{self.db_path}"


settings = Settings()
