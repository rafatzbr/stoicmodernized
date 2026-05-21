# 005 — TTS Generation

## Overview

The TTS generation stage converts narration text into spoken audio using Edge TTS only.

## Architecture

```
┌──────────────────────────────────────────────────┐
│               TTSStage                           │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  async run(scene_plan: dict)               │  │
│  │  → generates narration via Edge TTS        │  │
│  │  → processes scenes sequentially           │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  save_audio_path(audio_path: Path)         │  │
│  │  → stores path in job directory            │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Provider: EdgeTTS                         │  │
│  │  - Microsoft Edge TTS (free, fast)         │  │
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

### Provider Class (in `tts.py`)

| Class | Provider Enum | Description |
|-------|--------------|-------------|
| `EdgeTTS` | `TTSProvider.EDGE` | Microsoft Edge TTS (free, cloud) |

## Data Flow

1. **Input**: `ScenePlan` data from scene stage (loaded from `scenes.json`)
2. **Dispatch**: `TTSStage` validates that Edge TTS is selected
3. **Generate**: Edge TTS generates audio from narration text
4. **Output**: Audio file saved to `output/jobs/{job_id}/audio/narration.mp3`
5. **DB update**: `db.update_job(job_id, status="tts_complete", audio_path=...)`

## Business Rules

- **Provider selection**: `settings.tts_provider` must be `edge`. CLI flag `--provider` only accepts Edge aliases.
- **Audio output**: MP3 narration saved as `narration.mp3`; Edge subtitles saved as `narration.vtt`.
- **Mock mode**: Mock/local TTS is not supported; narration must come from Edge TTS.

## Cross-Package References

- **004 Scene Planning** — Input is `ScenePlan` data with narration segments
- **009 Video Rendering** — Audio file is input to FFmpeg/Remotion rendering

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.tts_provider` | TTSProvider | `TTSProvider.EDGE` | TTSStage validation |
| `settings.tts_voice` | str | `"en-US-GuyNeural"` | Stoic Modernized TTS voice selection |
| `settings.tts_speed` | float | `1.0` | TTS playback speed |
| `settings.background_music_volume` | float | `0.08` | Music volume in final mix |
| `settings.mock_mode` | bool | `False` | TTS mock mode is rejected |

## Integration Points

| External | Integration |
|----------|-------------|
| Microsoft Edge TTS | Free cloud TTS (edge provider) |
| SQLite | Persist job state |

## Non-Functional Requirements

- **Voice consistency**: Same voice is used throughout a video. Stoic Modernized uses `tts_voice`; The AI Signal uses `ai_signal_tts_voice`.
- **Speed control**: Playback speed adjustable via `tts_speed` (1.0 = normal).
- **Provider strictness**: The pipeline fails loudly if Edge TTS is unavailable instead of falling back to synthetic local audio.
