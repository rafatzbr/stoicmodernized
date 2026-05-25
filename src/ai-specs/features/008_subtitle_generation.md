# 008 — Subtitle Generation

## Overview

The subtitle generation stage creates synchronized subtitles using provider timing sidecars, optional forced alignment, Automatic Speech Recognition (ASR), or heuristic timing fallback. It can use Edge TTS VTT output, `stable-ts`/Whisper-family alignment against the exact narration transcript, Whisper (openai/whisper-tiny.en by default) to transcribe narration audio, and provider-neutral timing helpers for readable phrase-level WebVTT cues.

## Architecture

```
┌──────────────────────────────────────────────────┐
│              SubtitleStage                       │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  async run(job_id: str) → SubtitleResult   │  │
│  │  → runs ASR on narration audio             │  │
│  │  → generates SRT + WebVTT + JSON           │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  save_subtitle_result(result)              │  │
│  │  → writes subtitles.srt/.vtt + JSON        │  │
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

### Subtitle timing helpers (`src/subtitle_timing.py`)

| Class / Function | Purpose |
|------------------|---------|
| `TimedWord` | Provider-neutral word timing from native providers or aligners |
| `TimedCue` | Readable phrase-level cue with timing and source metadata |
| `group_words_into_readable_cues()` | Groups native/aligned words into readable cues instead of karaoke-style one-word captions |
| `make_heuristic_cues()` | Last-resort text + duration cue timing for audio-only providers |
| `parse_webvtt_cues()` | Normalizes EdgeTTS/WebVTT sidecars into `TimedCue` records |
| `write_webvtt()` | Deterministic WebVTT writer with dot-millisecond timestamps |

### SubtitleSegment (`src/models.py`)

| Field | Type | Description |
|-------|------|-------------|
| `start_time` | `float` | Segment start (seconds) |
| `end_time` | `float` | Segment end (seconds) |
| `text` | `str` | Transcribed text |
| `words` | `Optional[list[dict]]` | Word-level timing (optional) |

## Data Flow

1. **Input**: Narration audio from `output/jobs/{job_id}/audio/narration.wav`
2. **Native/sidecar timing**: Edge/native `audio/narration.vtt` is normalized first when present.
3. **Optional forced alignment**: If `tts_subtitles_timing=align` (or `auto` plus `tts_subtitles_alignment_enabled=true`), the stage aligns narration audio against the exact narration/script text through `stable-ts`/`stable_whisper` and groups aligned words into readable phrase cues.
4. **ASR fallback**: Whisper model transcribes audio with timing when alignment is disabled/unavailable or returns no usable words.
5. **Chunking**: Audio processed in chunks of `subtitle_asr_chunk_length_s` (20s by default)
6. **Timing normalization**: provider/native/aligned/fallback timings normalize through `src/subtitle_timing.py` when WebVTT is needed.
7. **Output**:
   - `subtitles.srt` — standard SRT format
   - `subtitles.vtt` — provider-neutral WebVTT sidecar generated from the final subtitle segments; this preserves readable phrase cues for audio-only/heuristic fallback providers as well as native/Edge timing paths
   - `subtitles.json` — structured JSON with segments and word timing
   - `audio/narration.vtt` — optional provider/native timing sidecar from TTS providers such as EdgeTTS, normalized before final subtitle artifacts are written
6. **Output directory**: `output/jobs/{job_id}/subtitles/`
7. **DB update**: `db.update_job(job_id, status="subtitles_complete", subtitle_path=...)`

## Business Rules

- **ASR model**: Default is `openai/whisper-tiny.en` — lightweight English-only model.
- **Language**: Default is `"english"` — configurable via `subtitle_asr_language`.
- **Subtitle toggle**: `subtitle_asr_enabled` controls whether subtitle generation runs.
- **Chunk length**: 20-second chunks balance accuracy and memory usage.
- **Word-level timing**: When available, each segment includes word-level start/end times for sync with Remotion word highlighting.
- **Cue style**: WebVTT output should be readable phrase-level cues for videos, not one-word karaoke captions.
- **Video-workflow subtitle sidecars**: `tts_subtitles_enabled` and `tts_subtitles_format` control whether the subtitle stage writes the final provider-neutral `subtitles.vtt` sidecar; this is scoped to video artifacts and does not change Hermes voice replies.
- **Scene-plan fallback retiming**: When subtitles fall back to scene-plan narration for audio-only providers, scale all scene cue boundaries to the measured narration duration. Do not clamp a longer estimated scene plan to audio duration without scaling, because that drops late narration from the VTT and leaves scenes/audio out of sync.

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
| `settings.tts_subtitles_enabled` | bool | `True` | Enable video subtitle sidecars |
| `settings.tts_subtitles_format` | str | `"vtt"` | Sidecar formats; `vtt`/`webvtt` writes `subtitles.vtt` |
| `settings.tts_subtitles_timing` | str | `"auto"` | Timing mode selector for native/alignment/heuristic paths |
| `settings.tts_subtitles_phrase_style` | str | `"readable"` | Readable phrase cue style for video captions |
| `settings.tts_subtitles_fallback` | str | `"heuristic"` | Fallback timing policy for audio-only providers |
| `settings.tts_subtitles_alignment_enabled` | bool | `False` | Allows `auto` timing mode to try forced alignment before ASR; explicit `tts_subtitles_timing=align` also attempts alignment |
| `settings.tts_subtitles_aligner` | str | `"stable-ts"` | Optional aligner backend; currently supports `stable-ts`/`stable_whisper` |
| `settings.tts_subtitles_aligner_model` | str | `"base.en"` | Whisper-family model name loaded by the aligner |

## Integration Points

| External | Integration |
|----------|-------------|
| stable-ts / stable_whisper | Optional forced alignment against the exact narration transcript |
| OpenAI Whisper (via whisper.cpp or API) | ASR transcription fallback |
| SQLite | Persist job state |

## Non-Functional Requirements

- **Model choice**: `whisper-tiny.en` is lightweight but limited to English. For multilingual, change `subtitle_asr_model` and `subtitle_asr_language`.
- **Processing time**: Subtitle generation is fast (< 30s for typical narration).
