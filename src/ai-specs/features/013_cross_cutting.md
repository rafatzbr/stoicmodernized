# 013 — Cross-Cutting Concerns

## Overview

Cross-cutting concerns include utility functions, logging, error handling, output capture, and provider-neutral subtitle timing helpers that are shared across pipeline stages. These are implemented in `src/utils.py`, `src/logging_config.py`, `src/main.py` (output capture), and `src/subtitle_timing.py`.

## Architecture

```
┌──────────────────────────────────────────────────┐
│           Cross-Cutting Concerns                 │
│                                                  │
│  ┌──────────────┐  ┌──────────────┐             │
│  │    utils.py  │  │ logging_     │             │
│  │              │  │ config.py    │             │
│  │              │  │              │             │
│  │ ensure_dir() │  │ JobLogger    │             │
│  │ get_job_dir()│  │ └── log_path │             │
│  │ get_stage_dir│  │ └── logger   │             │
│  │ save_json()  │  └──────────────┘             │
│  │ load_json()  │                               │
│  │ gen_job_id() │                               │
│  │ format_dur() │                               │
│  │ sanitize()   │                               │
│  │ split_chunks │  ┌──────────────┐             │
│  │ word_count() │  │  main.py     │             │
│  │ mock_resp()  │  │              │             │
│  └──────────────┘  │ TeeTextIO    │             │
│                    │ └── write()  │             │
│                    │ └── flush()  │             │
│                    │              │             │
│                    │ job_output_  │             │
│                    │ capture()    │             │
│                    │ └── context  │             │
│                    │   mgr        │             │
│                    └──────────────┘             │
└──────────────────────────────────────────────────┘
```

**Key files:** `src/utils.py`, `src/logging_config.py`, `src/main.py` (output capture), `src/subtitle_timing.py`

## Key Classes and Methods

### Utils (`src/utils.py`)

| Function | Signature | Purpose |
|----------|-----------|---------|
| `ensure_dir()` | `ensure_dir(path: Path) → Path` | Create directory if missing |
| `get_job_dir()` | `get_job_dir(job_id: str) → Path` | Get job output directory |
| `get_stage_dir()` | `get_stage_dir(job_id, stage) → Path` | Get stage subdirectory |
| `ensure_file_dir()` | `ensure_file_dir(path: Path) → Path` | Create parent dir of file |
| `save_json()` | `save_json(data, path: Path) → Path` | Write JSON to file |
| `load_json()` | `load_json(path: Path) → Any` | Read JSON from file |
| `generate_job_id()` | `generate_job_id() → str` | Generate UUID job ID |
| `format_duration()` | `format_duration(seconds: float) → str` | Format as HH:MM:SS.ms |
| `estimate_duration()` | `estimate_duration_from_words(word_count, wpm) → float` | Word count → seconds |
| `sanitize_filename()` | `sanitize_filename(name: str) → str` | Safe filename |
| `split_text_into_chunks()` | `split_text_into_chunks(text, max_words, overlap) → list[str]` | Text chunking |
| `word_count()` | `word_count(text: str) → int` | Word count |
| `generate_chapters()` | `generate_chapters_from_script(script: dict) → list[dict]` | Chapter generation |
| `create_directory_tree()` | `create_directory_tree(path: Path) → str` | Dir tree string |
| `mock_response()` | `mock_response(data: Any) → Any` | Mock passthrough |

### JobLogger (`src/logging_config.py`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `log_path` | Path | Path to job log file |
| `logger` | Logger | Python logging.Logger instance |

| Method | Signature | Purpose |
|--------|-----------|---------|
| `info()` | `info(msg: str)` | Log info message |
| `warning()` | `warning(msg: str)` | Log warning |
| `error()` | `error(msg: str)` | Log error |

### TeeTextIO (`src/main.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `write()` | `write(s: str) → int` | Write to all target streams |
| `flush()` | `flush()` | Flush all target streams |

### job_output_capture (`src/main.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `__enter__` | — | Start capturing stdout/stderr |
| `__exit__` | — | Stop capturing |

### Subtitle timing (`src/subtitle_timing.py`)

| Class / Function | Purpose |
|------------------|---------|
| `TimedWord` | Provider-neutral word timing model |
| `TimedCue` | Provider-neutral readable cue timing model |
| `group_words_into_readable_cues()` | Convert native/aligned word timings into readable phrase cues |
| `make_heuristic_cues()` | Approximate cue timing from transcript text and audio duration |
| `parse_webvtt_cues()` | Parse EdgeTTS/WebVTT sidecars into normalized `TimedCue` records |
| `write_webvtt()` | Format cue timing as deterministic WebVTT text for final `subtitles/subtitles.vtt` sidecars and provider/native VTT normalization |

## Data Flow

1. **Job creation**: `utils.get_job_dir(job_id)` creates `output/jobs/{job_id}/`
2. **Logger init**: `JobLogger(job_id)` creates `output/jobs/{job_id}/{job_id}.log`
3. **Stage execution**: Stage saves artifacts via `utils.save_json(data, path)`
4. **Output capture**: All stage commands optionally use `job_output_capture(job_id)` context manager
5. **Text mirroring**: `TeeTextIO` writes to both console and log file simultaneously
6. **JSON artifacts**: Every stage output is JSON (loaded via `utils.load_json()`)

## Business Rules

- **JSON standard**: All stage artifacts are JSON files with `indent=2` formatting.
- **UTF-8 encoding**: All file I/O uses UTF-8 encoding.
- **Directory creation**: All directories are created with `parents=True, exist_ok=True`.
- **Filename sanitization**: Filenames are limited to 100 characters with invalid chars removed.
- **Text chunking**: TTS uses 50-word chunks with 5-word overlap for smooth narration.
- **Chapter generation**: Default chapter count is 5 (Introduction, Sectors 1-3, Conclusion).

## Cross-Package References

- **All stages** — Every stage uses `utils.get_job_dir()`, `utils.save_json()`, `utils.load_json()`
- **All CLI commands** — Every command uses `JobLogger` for per-job logging
- **All CLI commands** — Stage commands use `job_output_capture()` for output logging
- **005 TTS Generation / 008 Subtitle Generation** — Video subtitle timing sidecars use `subtitle_timing.py` for normalized words, cues, heuristic audio-only fallback cues, and final `subtitles.vtt` formatting

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.jobs_dir` | Path | `output/jobs/` | All stages |
| `settings.project_root` | Path | `src/` parent | Root path resolution |
| `settings.tts_subtitles_*` | mixed | enabled/vtt/auto/readable/heuristic | Video-workflow subtitle timing sidecars only |

## Integration Points

| External | Integration |
|----------|-------------|
| File system | All stage artifact storage |
| Python logging | Job log files |

## Non-Functional Requirements

- **Idempotency**: `ensure_dir()` is safe to call multiple times.
- **Error resilience**: `load_json()` and `save_json()` use standard Python I/O — failures propagate to caller.
- **Concurrency**: No concurrency handling needed — pipeline is sequential.
- **File safety**: Filenames are sanitized to prevent injection/special characters.
