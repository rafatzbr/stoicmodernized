# 007 — Background Music

## Overview

The background music stage downloads or selects ambient background music for videos. Music is mixed at a low volume into the final audio during rendering. The stage supports curated music selection via a query-based approach.

## Architecture

```
┌──────────────────────────────────────────────────┐
│            BackgroundMusicStage                  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  run(job_id: str) → Path                   │  │
│  │  → downloads/locates music                 │  │
│  │  → validates duration                      │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  save_music_path(path: Path)               │  │
│  │  → stores path in job directory            │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**Key class:** `BackgroundMusicStage` in `src/stages/music.py`

## Key Classes and Methods

### BackgroundMusicStage (`src/stages/music.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `run()` | `run(job_id: str) → Path` | Obtain background music |
| `save_music_path()` | `save_music_path(path: Path)` | Persist music path |

## Data Flow

1. **Input**: `job_id` — music is associated with the job
2. **Music selection**: Based on `settings.background_music_query`
3. **Duration validation**: Music must be between `min_duration` (30s) and `max_duration` (600s)
4. **Output**: Music file saved to `output/jobs/{job_id}/audio/background_music.mp3`
5. **DB update**: `db.update_job(job_id, status="music_complete", music_path=...)`

## Business Rules

- **YouTube policy**: `youtube_allow_background_music_uploads` controls whether uploaded videos include background music. When False, background music is stripped during render.
- **Volume mixing**: Music is mixed at `settings.background_music_volume` (default 8%) to stay beneath narration.
- **Provider**: `background_music_provider` defaults to `"curated"` — no specific external integration yet.
- **Duration constraints**: Music must be between 30 seconds and 600 seconds (10 minutes).

## Cross-Package References

- **009 Video Rendering** — Background music is mixed during FFmpeg render

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.background_music_enabled` | bool | `True` | Music stage gate |
| `settings.background_music_provider` | str | `"curated"` | Music provider |
| `settings.background_music_query` | str | `"calm ambient instrumental"` | Music search query |
| `settings.background_music_min_duration` | int | `30` | Min duration (seconds) |
| `settings.background_music_max_duration` | int | `600` | Max duration (seconds) |
| `settings.background_music_volume` | float | `0.08` | Music volume in final mix (8%) |
| `settings.youtube_allow_background_music_uploads` | bool | `False` | YouTube policy flag |

## Integration Points

| External | Integration |
|----------|-------------|
| Music library/API | TBD — currently returns mock path |
| SQLite | Persist job state |

## Non-Functional Requirements

- **Low volume**: Music at 8% ensures narration remains primary audio.
- **Policy compliance**: YouTube background music detection is a known risk — the `youtube_allow_background_music_uploads` flag exists to mitigate.
