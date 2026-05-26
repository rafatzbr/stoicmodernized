# 005 — TTS Generation

## Overview

The TTS generation stage converts narration text into spoken audio using a selected provider. Edge TTS remains the cloud baseline with native WebVTT sidecars; Kokoro is the first local natural audio-only provider and relies on the subtitle stage's ASR/heuristic/optional forced-alignment sidecar path.

## Architecture

```
┌──────────────────────────────────────────────────┐
│               TTSStage                           │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  async run(scene_plan: dict)               │  │
│  │  → generates narration via TTS provider    │  │
│  │  → processes scenes sequentially           │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  save_audio_path(audio_path: Path)         │  │
│  │  → stores path in job directory            │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Providers: EdgeTTS, Kokoro                │  │
│  │  - Edge: cloud + native VTT sidecar        │  │
│  │  - Kokoro: local audio-only narration      │  │
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
| `EdgeTTSAudio` | `TTSProvider.EDGE` | Microsoft Edge TTS (free, cloud) with native `narration.vtt` sidecar |
| `KokoroTTSAudio` | `TTSProvider.KOKORO` | Local Kokoro audio-only provider; prefers direct `kokoro_onnx` file rendering when model files are configured and leaves VTT timing to subtitle fallback/alignment paths |

## Data Flow

1. **Input**: `ScenePlan` data from scene stage (loaded from `scenes.json`)
2. **Dispatch**: `TTSStage` normalizes provider aliases (`edge`/`edge-tts`, `kokoro`/`kokoro-tts`)
3. **Generate**: selected provider generates audio from narration text
4. **Output**: Audio file saved to `output/jobs/{job_id}/audio/narration.{format}`
   - Edge additionally writes `audio/narration.vtt`.
   - Kokoro intentionally does not write native timing; downstream subtitles write `subtitles/subtitles.vtt` from ASR/heuristic/optional forced-alignment timing.
5. **DB update**: `db.update_job(job_id, status="tts_complete", audio_path=...)`

## Business Rules

- **Provider selection**: `settings.tts_provider` defaults to `edge`. CLI flag `--provider` accepts `edge`/`edge-tts` and `kokoro`/`kokoro-tts` aliases.
- **Audio output**: Edge narration remains `narration.mp3`; Kokoro defaults to `narration.wav`; Edge subtitles are saved as `audio/narration.vtt`; Kokoro is audio-only.
- **Mock mode**: Mock TTS is not supported; narration must come from a real configured provider.

## Cross-Package References

- **004 Scene Planning** — Input is `ScenePlan` data with narration segments
- **009 Video Rendering** — Audio file is input to FFmpeg/Remotion rendering

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.tts_provider` | TTSProvider | `TTSProvider.EDGE` | TTSStage validation |
| `settings.tts_voice` | str | `"en-US-GuyNeural"` | Stoic Modernized TTS voice selection |
| `settings.tts_speed` | float | `1.0` | TTS playback speed |
| `settings.kokoro_command` | str | `"kokoro-tts"` | Local Kokoro CLI command |
| `settings.kokoro_voice` | str | `"bm_lewis"` | Kokoro voice ID; Rafael-approved Stoic Modernized default from the Kokoro voice bake-off |
| `settings.kokoro_speed` | Optional[float] | `0.85` | Kokoro narration speed; faster production pacing while avoiding the over-slow 0.66 pacing that made Shorts feel sluggish |
| `settings.kokoro_format` | str | `"wav"` | Kokoro narration file extension |
| `settings.kokoro_timeout_seconds` | float | `300.0` | Kokoro CLI timeout/fallback timeout |
| `settings.kokoro_model_path` | Optional[Path] | `~/.cache/kokoro-onnx/kokoro-v1.0.onnx` | Direct `kokoro_onnx` model path |
| `settings.kokoro_voices_path` | Optional[Path] | `~/.cache/kokoro-onnx/voices-v1.0.bin` | Direct `kokoro_onnx` voices path |
| `settings.kokoro_language` | str | `"en-gb"` | Kokoro language/accent code for Lewis |
| `settings.background_music_volume` | float | `0.08` | Music volume in final mix |
| `settings.mock_mode` | bool | `False` | TTS mock mode is rejected |

## Integration Points

| External | Integration |
|----------|-------------|
| Microsoft Edge TTS | Free cloud TTS (edge provider) |
| Kokoro ONNX / CLI fallback | Local natural audio-only TTS provider (`kokoro`) |
| SQLite | Persist job state |

## Non-Functional Requirements

- **Voice consistency**: Same voice is used throughout a video. Stoic Modernized uses `tts_voice`; The AI Signal uses `ai_signal_tts_voice`.
- **Speed control**: Playback speed adjustable via `tts_speed` (1.0 = normal).
- **Provider strictness**: The pipeline fails loudly if the selected provider command is unavailable instead of silently falling back to synthetic local audio.
- **Timing separation**: Local audio-only providers are valid even without native word timestamps because subtitle timing is handled by the provider-neutral subtitle stage.
