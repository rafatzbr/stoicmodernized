# 008 — Subtitle Generation

## Overview

The subtitle generation stage creates synchronized subtitles using Automatic Speech Recognition (ASR). It uses Whisper (openai/whisper-tiny.en by default) to transcribe the narration audio and produces both SRT and JSON subtitle formats with word-level timing.

## Architecture

```
┌──────────────────────────────────────────────────┐
│              SubtitleStage                       │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  async run(job_id: str) → SubtitleResult   │  │
│  │  → runs ASR on narration audio             │  │
│  │  → generates SRT + JSON                    │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  save_subtitle_result(result)              │  │
│  │  → writes subtitles.srt + subtitles.json   │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**Key class:** `SubtitleStage` in `src/stages/subtitles.py`

## Key Classes and Methods

### SubtitleStage (`src/stages/subtitles.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `run()` | `async run(job_id: str) → SubtitleResult` | Generate subtitles via ASR |
| `save_subtitle_result()` | `save_subtitle_result(result: SubtitleResult)` | Persist SRT + JSON |

### SubtitleResult (`src/models.py`)

| Field | Type | Description |
|-------|------|-------------|
| `srt_content` | `str` | SRT-formatted text |
| `segments` | `list[SubtitleSegment]` | Structured segments |
| `srt_path` | `str` | Path to .srt file |
| `json_path` | `str` | Path to .json file |

### SubtitleSegment (`src/models.py`)

| Field | Type | Description |
|-------|------|-------------|
| `start_time` | `float` | Segment start (seconds) |
| `end_time` | `float` | Segment end (seconds) |
| `text` | `str` | Transcribed text |
| `words` | `Optional[list[dict]]` | Word-level timing (optional) |

## Data Flow

1. **Input**: Narration audio from `output/jobs/{job_id}/audio/narration.wav`
2. **ASR**: Whisper model transcribes audio with timing
3. **Chunking**: Audio processed in chunks of `subtitle_asr_chunk_length_s` (20s by default)
4. **Output**: 
   - `subtitles.srt` — standard SRT format
   - `subtitles.json` — structured JSON with segments and word timing
5. **Output directory**: `output/jobs/{job_id}/subtitles/`
6. **DB update**: `db.update_job(job_id, status="subtitles_complete", subtitle_path=...)`

## Business Rules

- **ASR model**: Default is `openai/whisper-tiny.en` — lightweight English-only model.
- **Language**: Default is `"english"` — configurable via `subtitle_asr_language`.
- **Subtitle toggle**: `subtitle_asr_enabled` controls whether subtitle generation runs.
- **Chunk length**: 20-second chunks balance accuracy and memory usage.
- **Word-level timing**: When available, each segment includes word-level start/end times for sync with Remotion word highlighting.

## Cross-Package References

- **005 TTS Generation** — Input audio is narration from TTS stage
- **009 Video Rendering** — Subtitles are overlaid during rendering

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.subtitle_asr_enabled` | bool | `True` | Subtitle generation gate |
| `settings.subtitle_asr_model` | str | `"openai/whisper-tiny.en"` | Whisper model |
| `settings.subtitle_asr_language` | str | `"english"` | ASR language |
| `settings.subtitle_asr_chunk_length_s` | int | `20` | Audio chunk size |

## Integration Points

| External | Integration |
|----------|-------------|
| OpenAI Whisper (via whisper.cpp or API) | ASR transcription |
| SQLite | Persist job state |

## Non-Functional Requirements

- **Model choice**: `whisper-tiny.en` is lightweight but limited to English. For multilingual, change `subtitle_asr_model` and `subtitle_asr_language`.
- **Processing time**: Subtitle generation is fast (< 30s for typical narration).
