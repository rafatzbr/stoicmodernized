# 001 — Pipeline CLI & Job Lifecycle

## Overview

The `stoic-modernized` CLI is the entry point for the entire video production pipeline. Built with **Typer** (a modern wrapper around Click), it provides a set of commands that represent both individual pipeline stages and the full pipeline. Every command operates on a **job** — a uniquely identified instance of the pipeline with its own directory under `output/jobs/<job_id>/`.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    CLI (main.py)                     │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │  idea()  │  │research()│  │ script() / scene()│  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │   tts()  │  │ images() │  │ music() / subs()  │  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │  render()│  │ metadata()│  │   upload()        │  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │  jobs()  │  │ status() │  │    retry()        │  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
│  ┌───────────────────────────────────────────────┐   │
│  │              run() (full pipeline)            │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │        job_output_capture() (context mgr)     │   │
│  │  captures stdout/stderr → job log file       │   │
│  └───────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

**Key class:** `app = typer.Typer(...)` in `src/main.py`

## Key Classes and Methods

### CLI App (`src/main.py`)

| Method | Command | Arguments | Purpose |
|--------|---------|-----------|---------|
| `idea()` | `idea` | `--count`, `--niche`, `--mock` | Generate topic ideas (mock only) |
| `research()` | `research` | `<topic>`, `--job-id`, `--mock` | Run research stage |
| `script()` | `script` | `<job_id>`, `--mock`, `--video-mode` | Generate video script |
| `scene()` | `scene` | `<job_id>`, `--mock` | Create scene plan |
| `tts()` | `tts` | `<job_id>`, `--provider`, `--mock` | Generate narration audio |
| `images()` | `images` | `<job_id>`, `--provider`, `--mock` | Generate images |
| `music()` | `music` | `<job_id>` | Download background music |
| `subtitles()` | `subtitles` | `<job_id>`, `--mock` | Generate subtitles via ASR |
| `render()` | `render` | `<job_id>`, `--mock`, `--video-mode`, `--renderer-type`, `--platform`, `--skip-upload` | Render video (single or multi) |
| `metadata()` | `metadata` | `<job_id>`, `--mock` | Generate metadata |
| `upload()` | `upload` | `<job_id>`, `--mock`, `--video-path` | Upload to YouTube |
| `run()` | `run` | `<topic>`, `--mock`, `--provider`, `--skip-upload` | Full pipeline from topic to upload |
| `jobs()` | `jobs` | `--status` | List all jobs |
| `retry()` | `retry` | `<job_id>`, `--stage`, `--mock` | Retry a specific stage |
| `status()` | `status` | `<job_id>` | Show job details |

### Job Lifecycle

```
PENDING → RUNNING → * → COMPLETED / FAILED
```

Status transitions:
- `PENDING` → `RUNNING` — when a command starts (implicit, not set explicitly in code, but stages set intermediate statuses like `research_complete`, `script_complete`, etc.)
- Intermediate statuses: `research_complete`, `script_complete`, `scene_complete`, `images_complete`, `subtitles_complete`, `ready_for_upload`
- `COMPLETED` — final state (set implicitly after `render()` completes)
- `FAILED` — when an unhandled exception occurs

### Output Capture (`job_output_capture`)

```python
@contextlib.contextmanager
def job_output_capture(job_id: str):
    log_dir = settings.jobs_dir / job_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{job_id}.log"
    # ... redirects stdout/stderr to both console and log file
```

Uses `TeeTextIO` to mirror writes to both the console and the log file simultaneously.

## Data Flow

1. **Command invocation** → `main.py` parses Typer CLI arguments
2. **Job lookup** → `_load_job_record(job_id)` fetches from SQLite via `db.get_job(job_id)`
3. **Logger init** → `JobLogger(job_id)` creates per-job logger with dedicated log file
4. **Stage instantiation** → `StageClass(job_id=job_id, mock=mock)`
5. **Stage execution** → `asyncio.run(stage.run(...))`
6. **Artifact save** → `stage.save_*()` writes JSON to `output/jobs/{job_id}/{stage}/`
7. **DB update** → `db.update_job(job_id, status="*_complete", <artifact>_path=...)`
8. **Console output** → Rich-formatted tables and status messages

### Full Pipeline (`run()` command)

```
idea() → research() → script() → scene() → tts() → images() → music() → subtitles() → render() → metadata() → upload()
```

Each stage is executed sequentially. The `run()` command is the one-shot pipeline runner. Individual commands allow stage-level operation.

## Business Rules

- **Mock mode** (`--mock` or `settings.mock_mode`): Bypasses external calls (LLM, TTS, image gen, YouTube API) and returns static/deterministic data.
- **Job isolation**: Each job has its own directory under `output/jobs/<job_id>/` with subdirectories for each stage.
- **Stage dependencies**: Each stage requires the output of the previous stage (e.g., `script()` requires `research_path` from `research()`). Commands validate this and exit with error if missing.
- **Video mode**: `--video-mode` controls whether short (60s, 1080x1920, vertical) or long (900s, 1920x1080, landscape) video is produced.
- **Render modes**: `render()` can produce both landscape and portrait in a single run (dual render).
- **Retry**: The `retry()` command supports retrying the entire pipeline or a specific stage.

## Cross-Package References

- **012 Persistence** — `database.py` provides `db.create_job()`, `db.get_job()`, `db.get_all_jobs()`, `db.update_job()`
- **011 Configuration** — `config.py` provides `settings` singleton with all configuration
- **002–010** — Each feature spec describes the corresponding stage

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.jobs_dir` | Path | `output/jobs/` | All stages, main.py |
| `settings.db_path` | Path | `stoic.db` | database.py |
| `settings.mock_mode` | bool | `False` | All stages, main.py |
| `settings.default_video_mode` | VideoMode | `VideoMode.SHORT` | main.py run() |
| `settings.video_fps` | int | `30` | render.py, remotion_renderer.py |
| `settings.video_width` | int | `1920` | render.py, remotion_renderer.py |
| `settings.video_height` | int | `1080` | render.py, remotion_renderer.py |
| `settings.short_video_width` | int | `1080` | remotion_renderer.py |
| `settings.short_video_height` | int | `1920` | remotion_renderer.py |

## Integration Points

| External | Integration |
|----------|-------------|
| SQLite (via SQLAlchemy) | Local database for job tracking |
| Typer CLI | CLI framework — no external integration, just the library |

## Non-Functional Requirements

- **Reliability**: Each stage is independently retryable via `retry()` command.
- **Observability**: Per-job log files capture all stdout/stderr. `status()` and `jobs()` commands query the database.
- **Error handling**: Stage-specific errors (e.g., `ScriptGenerationError`) are caught, logged, and stored in the job record's `error_message` field.
- **Determinism**: Mock mode ensures reproducible testing without external dependencies.
