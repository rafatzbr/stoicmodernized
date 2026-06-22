"""Configuration and settings for the stoic-modernized pipeline."""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class TTSProvider(str, Enum):
    """Supported TTS providers."""

    EDGE = "edge"
    KOKORO = "kokoro"


class ImageProvider(str, Enum):
    """Supported image generation providers."""

    CODEX_IMAGE = "codex_image"
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


class Channel(str, Enum):
    """Supported channel pipelines."""

    STOIC_MODERNIZED = "stoic-modernized"


class RemotionPlatform(str, Enum):
    """Supported Remotion visual platform presets."""

    YOUTUBE = "youtube"
    TIKTOK = "tiktok"


class Settings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    project_root: Path = PROJECT_ROOT
    output_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "output")
    jobs_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "output" / "jobs")

    db_path: Path = Field(default_factory=lambda: PROJECT_ROOT / "stoic.db")

    # Stoic Modernized
    channel_name: str = "Stoic Modernized"
    channel_handle: str = "@stoicmodernized"
    channel_description: str = "Ancient logic for the high-performance digital age"
    channel_voice: str = "calm, practical, concise, modern, not preachy, not academic"

    default_channel: Channel = Channel.STOIC_MODERNIZED
    default_video_mode: VideoMode = VideoMode.SHORT
    video_width: int = 1920
    video_height: int = 1080
    short_video_width: int = 1080
    short_video_height: int = 1920
    short_max_duration_seconds: int = 60
    short_target_scene_count: int = 6
    long_max_duration_seconds: int = 900
    video_fps: int = 30
    background_music_volume: float = 0.03
    background_music_enabled: bool = True
    background_music_provider: str = "curated"
    background_music_query: str = "calm ambient instrumental background music"
    background_music_min_duration: int = 30
    background_music_max_duration: int = 600
    youtube_allow_background_music_uploads: bool = True

    tts_provider: TTSProvider = TTSProvider.EDGE
    tts_voice: str = Field(default="en-US-GuyNeural", validation_alias=AliasChoices("TTS_VOICE", "TS_VOICE"))
    tts_speed: float = 1.0
    narration_prep_enabled: bool = False  # Enable narration preparation for natural TTS delivery
    tts_api_key: Optional[str] = None
    kokoro_command: str = "kokoro-tts"
    kokoro_voice: str = "bm_lewis"
    kokoro_speed: Optional[float] = 0.85
    kokoro_format: str = "wav"
    kokoro_timeout_seconds: float = 300.0
    kokoro_model_path: Optional[Path] = Path.home() / ".cache" / "kokoro-onnx" / "kokoro-v1.0.onnx"
    kokoro_voices_path: Optional[Path] = Path.home() / ".cache" / "kokoro-onnx" / "voices-v1.0.bin"
    kokoro_language: str = "en-gb"

    subtitle_asr_enabled: bool = True
    subtitle_asr_model: str = "openai/whisper-tiny.en"
    subtitle_asr_language: str = "english"
    subtitle_asr_chunk_length_s: int = 20
    tts_subtitles_enabled: bool = True
    tts_subtitles_format: str = "vtt"
    tts_subtitles_timing: str = "auto"
    tts_subtitles_phrase_style: str = "readable"
    tts_subtitles_fallback: str = "heuristic"
    tts_subtitles_alignment_enabled: bool = True
    tts_subtitles_aligner: str = "stable-ts"
    tts_subtitles_aligner_model: str = "base.en"

    sd_cli_path: str = "/home/rafatz/dev/stable-diffusion.cpp/build/bin/sd-cli"
    sd_model_path: str = "/data/sd-models/sd3.5_large.safetensors"
    sd_clip_l_path: str = "/data/sd-models/clip_l.safetensors"
    sd_clip_g_path: str = "/data/sd-models/clip_g.safetensors"
    sd_t5xxl_path: str = "/data/sd-models/t5xxl_fp16.safetensors"
    sd_image_width: int = 544
    sd_image_height: int = 960
    sd_cfg_scale: float = 3.8
    sd_steps: int = 20
    sd_sampling_method: str = "euler"
    sd_negative_prompt: str = "blurry, low quality, deformed, extra people in foreground, cluttered desk, text, logo, watermark, overexposed, bad hands, extra fingers, missing fingers, duplicate objects, malformed laptop, distorted pen, plastic skin, uncanny smile, centered headshot, stiff stock photo pose, oversmoothed skin, multiple computers"
    image_provider: ImageProvider = ImageProvider.CODEX_IMAGE
    codex_image_command: str = "hermes"
    codex_image_timeout_seconds: float = 900.0
    codex_image_aspect_ratio: str = "portrait"
    force_placeholder_images: bool = False

    sd_server_url: str = "http://localhost:1234"
    sd_server_api_path: str = "/sdapi/v1/txt2img"
    sd_server_timeout_seconds: float = 1800.0

    youtube_api_key: Optional[str] = None
    youtube_credentials_path: Optional[str] = None
    youtube_privacy_status: YouTubePrivacy = YouTubePrivacy.UNLISTED
    youtube_schedule_datetime: Optional[str] = None

    # Cross-platform short-form distribution (Meta APIs first, TikTok API second)
    social_distribution_enabled: bool = False
    social_distribution_platforms: str = "instagram,facebook,tiktok"
    meta_graph_api_version: str = "v25.0"
    meta_app_id: Optional[str] = None
    meta_app_secret: Optional[str] = None
    meta_page_access_token: Optional[str] = None
    instagram_user_id: Optional[str] = None
    facebook_page_id: Optional[str] = None
    social_video_public_base_url: Optional[str] = None
    tiktok_access_token: Optional[str] = None
    tiktok_open_id: Optional[str] = None
    tiktok_privacy_level: str = "SELF_ONLY"

    local_llm_base_url: str = "http://localhost:8080/v1/chat/completions"
    local_llm_model: str = "local"
    local_llm_timeout_seconds: float = 300.0
    local_llm_max_tokens: int = 32

    local_script_model: Optional[str] = None
    local_script_max_tokens: int = 1800
    local_script_temperature: float = 0.7
    local_script_timeout_seconds: float = 30.0
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

    def get_channel_name(self, channel: Channel) -> str:
        return self.channel_name

    def get_channel_handle(self, channel: Channel) -> str:
        return self.channel_handle

    def get_channel_description(self, channel: Channel) -> str:
        return self.channel_description

    def get_channel_voice(self, channel: Channel) -> str:
        return self.channel_voice

    def get_channel_tts_voice(self, channel: Channel) -> str:
        return self.tts_voice

    def get_channel_cta(self, channel: Channel) -> str:
        return "Subscribe to @stoic-modernized for practical Stoic tools you can use at work."

    def get_channel_tags(self, channel: Channel) -> list[str]:
        return [
            "stoicism",
            "stoic philosophy",
            "modern stoicism",
            "stoic modernized",
            "ancient wisdom",
            "personal development",
            "mindfulness",
            "productivity",
            "career advice",
            "workplace stress",
        ]


settings = Settings()
