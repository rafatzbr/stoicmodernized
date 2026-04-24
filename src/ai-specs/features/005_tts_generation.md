# 005 — TTS Generation

## Overview

The TTS generation stage converts narration text into spoken audio using a pluggable provider architecture. Currently supported providers: `local`, `edge`, `elevenlabs`, `voxcpm`. Each provider has different quality, cost, and latency characteristics.

## Architecture

```
┌──────────────────────────────────────────────────┐
│               TTSStage                           │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  async run(scene_plan: dict)               │  │
│  │  → dispatches to provider based on         │  │
│  │     settings.tts_provider                  │  │
│  │  → processes scenes sequentially           │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  save_audio_path(audio_path: Path)         │  │
│  │  → stores path in job directory            │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Providers (selected by type):             │  │
│  │  - VoxCPMTTS   (local, high quality)       │  │
│  │  - EdgeTTS     (free, fast)                │  │
│  │  - ElevenLabs  (premium, best quality)     │  │
│  │  - LocalTTS    (basic, local)              │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**Key class:** `TTSStage` in `src/stages/tts.py`

## Key Classes and Methods

### TTSStage (`src/stages/tts.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `run()` | `async run(scene_plan: dict) → Path` | Generate audio via provider |
| `save_audio_path()` | `save_audio_path(path: Path)` | Persist audio path to job |

### Provider Classes (in `tts.py`)

| Class | Provider Enum | Description |
|-------|--------------|-------------|
| `VoxCPMTTS` | `TTSProvider.VOXCPM` | Tokenizer-free multilingual TTS via VoxCPM.cpp CLI |
| `EdgeTTS` | `TTSProvider.EDGE` | Microsoft Edge TTS (free, cloud) |
| `ElevenLabsTTS` | `TTSProvider.ELEVENLABS` | ElevenLabs API (premium) |
| `LocalTTS` | `TTSProvider.LOCAL` | Basic local TTS |

## Data Flow

1. **Input**: `ScenePlan` data from scene stage (loaded from `scenes.json`)
2. **Dispatch**: `_dispatch_tts()` selects provider based on `settings.tts_provider`
3. **Generate**: Selected provider generates audio from narration text
4. **Output**: Audio file saved to `output/jobs/{job_id}/audio/narration.wav`
5. **DB update**: `db.update_job(job_id, status="tts_complete", audio_path=...)`

## Business Rules

- **Provider selection**: Determined by `settings.tts_provider` (enum: `local`, `edge`, `elevenlabs`, `voxcpm`). CLI flag `--provider` overrides.
- **VoxCPM specifics**: Tokenizer-free model, supports multiple languages. Configurable via `voice`, `speed`, `cfg_value`, `inference_timesteps`, `threads`. Supports `cpu`, `cuda`, `vulkan` backends.
- **Audio output**: Always WAV format, saved as `narration.wav`.
- **Mock mode**: Returns a mock audio path without generating actual audio.

## Cross-Package References

- **004 Scene Planning** — Input is `ScenePlan` data with narration segments
- **009 Video Rendering** — Audio file is input to FFmpeg/Remotion rendering

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.tts_provider` | TTSProvider | `TTSProvider.LOCAL` | TTSStage dispatch |
| `settings.tts_voice` | str | `"en-US-GuyNeural"` | TTS voice selection |
| `settings.tts_speed` | float | `1.0` | TTS playback speed |
| `settings.tts_api_key` | Optional[str] | `None` | API key for cloud providers |
| `settings.background_music_volume` | float | `0.08` | Music volume in final mix |
| `settings.mock_mode` | bool | `False` | Mock mode gate |

## Integration Points

| External | Integration |
|----------|-------------|
| Microsoft Edge TTS | Free cloud TTS (edge provider) |
| ElevenLabs API | Premium TTS (elevenlabs provider) |
| VoxCPM.cpp CLI | Local TTS via external CLI tool |
| SQLite | Persist job state |

## Non-Functional Requirements

- **Voice consistency**: Same voice (`tts_voice`) used throughout a video.
- **Speed control**: Playback speed adjustable via `tts_speed` (1.0 = normal).
- **Provider flexibility**: Easy to add new providers by following the existing class pattern.
