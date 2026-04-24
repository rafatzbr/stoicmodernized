# 012 — Persistence Layer

## Overview

The persistence layer manages job lifecycle state using SQLite via SQLAlchemy. It tracks job creation, progress, artifacts, and completion status. All stages interact with the database to update job state.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                database.py                       │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  db (global instance)                      │  │
│  │  └── SQLite connection                     │  │
│  │  └── Job model (SQLAlchemy ORM)            │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  Operations:                                     │
│  ├── create_job(topic) → Job                    │  │
│  ├── get_job(job_id) → Optional[Job]            │  │
│  ├── get_all_jobs(status=None) → list[Job]      │  │
│  └── update_job(job_id, ...) → None             │  │
└──────────────────────────────────────────────────┘
```

**Key class:** `db` instance in `src/database.py`
**Key model:** `Job` in `src/models.py` (SQLAlchemy model)

## Key Classes and Methods

### Job (SQLAlchemy Model — `src/models.py`)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `job_id` | String (UUID) | No | Primary key |
| `topic` | String | No | Video topic |
| `status` | String | No | Job status |
| `created_at` | DateTime | No | Creation time |
| `updated_at` | DateTime | No | Last update time |
| `started_at` | DateTime | Yes | Pipeline start time |
| `completed_at` | DateTime | Yes | Pipeline end time |
| `error_message` | Text | Yes | Error if failed |
| `research_path` | String | Yes | Path to research.json |
| `script_path` | String | Yes | Path to script.json |
| `scene_plan_path` | String | Yes | Path to scenes.json |
| `images_dir` | String | Yes | Path to images/ |
| `audio_path` | String | Yes | Path to narration audio |
| `subtitle_path` | String | Yes | Path to subtitles |
| `video_path` | String | Yes | Path to rendered video |
| `thumbnail_path` | String | Yes | Path to thumbnail |
| `metadata_path` | String | Yes | Path to metadata |
| `log_path` | String | Yes | Path to job log file |

### Job (Pydantic Model — `src/models.py`)

Used for serialization/serialization boundary:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `job_id` | str | uuid4() | Unique job identifier |
| `topic` | str | — | Video topic |
| `status` | JobStatus | `PENDING` | Current status |
| `created_at` | datetime | now(UTC) | Creation timestamp |
| `updated_at` | datetime | now(UTC) | Last update timestamp |
| `started_at` | Optional[datetime] | None | Pipeline start |
| `completed_at` | Optional[datetime] | None | Pipeline end |
| `error_message` | Optional[str] | None | Error text |
| `research_path` | Optional[str] | None | File path |
| `script_path` | Optional[str] | None | File path |
| `scene_plan_path` | Optional[str] | None | File path |
| `images_dir` | Optional[str] | None | Directory path |
| `audio_path` | Optional[str] | None | File path |
| `subtitle_path` | Optional[str] | None | File path |
| `video_path` | Optional[str] | None | File path |
| `thumbnail_path` | Optional[str] | None | File path |
| `metadata_path` | Optional[str] | None | File path |
| `log_path` | Optional[str] | None | File path |

### Database Operations (`src/database.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `create_job()` | `create_job(topic: str) → Job` | Create new job record |
| `get_job()` | `get_job(job_id: str) → Optional[Job]` | Fetch single job |
| `get_all_jobs()` | `get_all_jobs(status: Optional[str]) → list[Job]` | List all jobs (optional filter) |
| `update_job()` | `update_job(job_id: str, **fields)` | Update job fields |

## Data Flow

1. **Job creation**: `db.create_job(topic)` → creates record with status `PENDING`, generates UUID
2. **Status updates**: Each stage calls `db.update_job(job_id, status="*_complete", <path_field>=path)`
3. **Job retrieval**: CLI commands call `db.get_job(job_id)` to load job context
4. **Job listing**: `db.get_all_jobs(status)` used by `jobs()` CLI command
5. **Error tracking**: Failed stages set `error_message` and status to `FAILED`

## Business Rules

- **UUID job IDs**: Each job gets a unique UUID via `uuid4()`.
- **Auto-timestamps**: `created_at` and `updated_at` are set on creation/update.
- **Path tracking**: Every stage output path is stored in the job record for retrieval.
- **Status progression**: Jobs flow `PENDING → RUNNING → *_complete → COMPLETED / FAILED`.
- **Nullable paths**: All artifact paths are `Optional[str]` — they're filled in as stages complete.

## Cross-Package References

- **001 Pipeline CLI** — All commands use `db.create_job()`, `db.get_job()`, `db.update_job()`
- **All stages** — Each stage updates job status and artifact paths after completion
- **011 Configuration** — `settings.db` provides the SQLite connection string

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.db_path` | Path | `stoic.db` | Database location |
| `settings.db` | str | `"sqlite:///{db_path}"` | SQLAlchemy engine URL |

## Integration Points

| External | Integration |
|----------|-------------|
| SQLite | Local embedded database |
| SQLAlchemy | ORM layer |

## Non-Functional Requirements

- **No migrations needed**: Single-table schema — no version management required.
- **Thread safety**: SQLite with single-writer — pipeline is sequential, so no concurrent writes.
- **Data retention**: Job records persist indefinitely until manually deleted.
- **Recovery**: `retry()` command reads job record to resume from any stage.
