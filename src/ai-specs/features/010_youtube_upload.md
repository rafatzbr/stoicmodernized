# 010 — YouTube Upload

## Overview

The YouTube upload stage uploads rendered videos to YouTube using the YouTube Data API v3. It handles authentication, metadata setting, chapter marking, and privacy configuration. It supports both immediate upload and scheduled publishing.

## Architecture

```
┌──────────────────────────────────────────────────┐
│              YouTubeUploader                     │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  upload(video_path: str, metadata: dict)   │  │
│  │  → authenticates via OAuth2                │  │
│  │  → uploads video file                      │  │
│  │  → sets metadata (title, desc, tags)       │  │
│  │  → sets chapters                           │  │
│  │  → sets privacy/status                     │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**Key class:** `YouTubeUploader` in `src/stages/upload.py`

## Key Classes and Methods

### YouTubeUploader (`src/stages/upload.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `upload()` | `upload(video_path: str, metadata: dict) → UploadResult` | Upload to YouTube |

### UploadResult (`src/models.py`)

| Field | Type | Description |
|-------|------|-------------|
| `video_id` | Optional[str] | YouTube video ID |
| `video_url` | Optional[str] | YouTube video URL |
| `upload_status` | str | Success/failure status |
| `error` | Optional[str] | Error message if failed |

### YouTubeMetadata (`src/models.py`)

| Field | Type | Description |
|-------|------|-------------|
| `title` | str | Video title |
| `description` | str | Video description |
| `tags` | list[str] | Tags |
| `chapters` | list[dict] | Chapter markers |
| `privacy_status` | str | `public`, `unlisted`, `private` |
| `scheduled_publish_datetime` | Optional[str] | Scheduled publish time |

## Data Flow

1. **Input**: Video path from render stage, metadata from metadata stage
2. **Authentication**: OAuth2 credentials loaded from `settings.youtube_credentials_path`
3. **Upload**: Video file uploaded via YouTube Data API
4. **Metadata**: Title, description, tags set on the uploaded video
5. **Chapters**: YouTube chapters created from script chapters
6. **Privacy**: Set via `youtube_privacy_status` setting
7. **Output**: Upload result with video ID and URL
8. **DB update**: `db.update_job(job_id, status="completed", video_path=..., video_url=...)`

## Business Rules

- **Privacy**: Default is `unlisted`. Configurable via `youtube_privacy_status`.
- **Scheduling**: `youtube_schedule_datetime` allows future scheduled publishing.
- **Mock mode**: In mock mode, skips actual upload and returns mock result.
- **Background music flag**: If `youtube_allow_background_music_uploads` is False, the upload may be skipped or a warning is issued (content policy risk).
- **Channel branding**: Video description includes channel name and handle.

## Cross-Package References

- **009 Video Rendering** — Input is rendered video file
- **003 Script Generation** — Chapters come from script chapters
- **011 Configuration** — Channel name, handle, API keys

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.youtube_api_key` | Optional[str] | `None` | YouTube API key |
| `settings.youtube_credentials_path` | Optional[str] | `None` | OAuth2 credentials |
| `settings.youtube_privacy_status` | YouTubePrivacy | `unlisted` | Privacy setting |
| `settings.youtube_schedule_datetime` | Optional[str] | `None` | Schedule time |
| `settings.channel_name` | str | `"Stoic Modernized"` | Video description |
| `settings.channel_handle` | str | N/A | Video description |
| `settings.ai_signal_channel_handle` | str | `"@TheAISignalNews"` | AI Signal channel |
| `settings.channel_description` | str | `"Ancient logic..."` | Video description |
| `settings.mock_mode` | bool | `False` | Mock mode gate |

## Integration Points

| External | Integration |
|----------|-------------|
| YouTube Data API v3 | Video upload, metadata, chapters |
| OAuth2 | Authentication |
| SQLite | Persist job state |

## Non-Functional Requirements

- **Authentication**: Requires OAuth2 credentials (Google Cloud console setup needed).
- **Upload size**: No explicit size limit — YouTube handles large files.
- **Processing time**: YouTube processing time is outside control (HD processing can take minutes to hours).
- **Retry**: Failed uploads can be retried via `retry()` command.
