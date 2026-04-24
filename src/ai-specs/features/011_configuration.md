# 011 — Configuration & Channel Selection

## Overview

The configuration module (`src/config.py`) provides all application settings via a Pydantic `BaseSettings` singleton. It supports environment variable loading (`.env` file), default values, and type coercion. It also defines channel templates for different content pipelines.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                 config.py                        │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Settings (BaseSettings)                   │  │
│  │  └── model_config: .env loading           │  │
│  │  └── ~60 config fields                    │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  Enums:                                          │
│  ├── TTSProvider (local, edge, elevenlabs, ...)  │  │
│  ├── ImageProvider (sd_cli, sd_server, ...)      │  │
│  ├── YouTubePrivacy (public, unlisted, private)  │  │
│  ├── VideoMode (short, long)                     │  │
│  ├── Channel (stoic-modernized, ai-signal)       │  │
│  └── RemotionPlatform (youtube, tiktok)          │  │
│                                                  │
│  settings = Settings()  # Singleton              │  │
└──────────────────────────────────────────────────┘
```

**Key class:** `Settings` in `src/config.py`
**Key instance:** `settings = Settings()` (singleton, imported everywhere)

## Key Classes and Enums

### Settings (`src/config.py`)

The `Settings` class inherits from `pydantic_settings.BaseSettings` with the following model config:
- `env_file=".env"` — loads from `.env` in project root
- `env_file_encoding="utf-8"`
- `case_sensitive=False` — env vars are case-insensitive
- `extra="ignore"` — unknown env vars are silently ignored

Key properties:
- `db` property → returns SQLite connection string `"sqlite:///{db_path}"`

### Enums

| Enum | Values | Usage |
|------|--------|-------|
| `TTSProvider` | `local`, `edge`, `elevenlabs`, `voxcpm` | TTS provider selection |
| `ImageProvider` | `sd_cli`, `sd_server`, `dall_e` | Image generation provider |
| `YouTubePrivacy` | `public`, `unlisted`, `private` | YouTube video privacy |
| `VideoMode` | `short`, `long` | Output video mode |
| `Channel` | `stoic-modernized`, `ai-signal` | Content channel pipeline |
| `RemotionPlatform` | `youtube`, `tiktok` | Remotion visual preset |

## Data Flow

1. **Settings loaded**: `settings = Settings()` on module import
2. **Env file**: `.env` in project root is auto-loaded
3. **Usage**: Every module imports `from src.config import settings` and reads values directly
4. **CLI overrides**: Some settings can be overridden via CLI flags (e.g., `--provider`, `--video-mode`)

## Business Rules

- **Channel switching**: `default_channel` selects between `"Stoic Modernized"` and `"AI Signal"` templates. Each has its own:
  - `channel_name` / `ai_signal_channel_name`
  - `channel_voice` / `ai_signal_channel_voice`
  - `ai_signal_channel_handle`
- **Video mode**: `default_video_mode` controls whether short or long videos are produced by default.
- **TTS voice**: `tts_voice` has an alias: `TTS_VOICE` or `TS_VOICE` env vars both map to it.
- **Config immutability**: Settings are loaded once at startup and treated as read-only during pipeline execution.

## Cross-Package References

- **All stages** — Every stage reads from `settings`
- **001 Pipeline CLI** — CLI commands read mode/privacy/provider from settings
- **003 Script** — Channel voice affects script tone
- **012 Persistence** — `settings.db` returns the SQLite connection string

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.project_root` | Path | `src/` parent | Root path resolution |
| `settings.output_dir` | Path | `output/` | All stage outputs |
| `settings.jobs_dir` | Path | `output/jobs/` | Job-specific outputs |
| `settings.db_path` | Path | `stoic.db` | Database location |
| `settings.default_channel` | Channel | `stoic-modernized` | Channel template |
| `settings.default_video_mode` | VideoMode | `short` | Default video mode |
| `settings.video_width` | int | `1920` | Landscape video |
| `settings.video_height` | int | `1080` | Landscape video |
| `settings.short_video_width` | int | `1080` | Portrait video |
| `settings.short_video_height` | int | `1920` | Portrait video |
| `settings.video_fps` | int | `30` | Video framerate |
| `settings.mock_mode` | bool | `False` | Mock mode gate |
| `settings.tts_provider` | TTSProvider | `local` | TTS provider |
| `settings.youtube_privacy_status` | YouTubePrivacy | `unlisted` | YouTube privacy |
| `settings.background_music_volume` | float | `0.08` | Music volume (8%) |
| `settings.background_music_enabled` | bool | `True` | Music gate |
| `settings.subtitle_asr_enabled` | bool | `True` | Subtitle gate |
| `settings.force_placeholder_images` | bool | `False` | Image skip |

## Integration Points

| External | Integration |
|----------|-------------|
| `.env` file | Environment variable configuration |
| Environment variables | Runtime configuration override |

## Non-Functional Requirements

- **Single source of truth**: All config is in one `Settings` class — no scattered defaults.
- **Type safety**: Pydantic validates types and coerces values (e.g., `"30"` → `30` for int fields).
- **Extensibility**: Adding a new provider requires only adding an enum value and config fields.
