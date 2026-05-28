# 009 — Video Rendering

## Overview

The video rendering stage produces the final video file from all pipeline artifacts (images, audio, subtitles, music). Two renderers are available:

1. **FFmpeg Renderer** (`VideoRenderer`) — Simple, single-pass, ffmpeg-based
2. **Remotion Renderer** (`RemotionRenderer`) — Production-quality, React-based, with composable scenes

The renderer is selected via `--renderer-type` flag: `"ffmpeg"` or `"remotion"`.

## Architecture

```
┌──────────────────────────────────────────────────┐
│              Rendering Pipeline                  │
│                                                  │
│  ┌─────────────────┐    ┌────────────────────┐  │
│  │  VideoRenderer  │    │ RemotionRenderer   │  │
│  │                 │    │                    │  │
│  │  ffmpeg-based   │    │  React/TypeScript  │  │
│  │  Single-pass    │    │  Composable        │  │
│  │  Quick          │    │  Effects           │  │
│  └─────────────────┘    └────────────────────┘  │
│                                                  │
│  Common inputs:                                  │
│  ├── images/scene_XXX.jpg                       │  │
│  ├── audio/narration.wav                        │  │
│  ├── audio/background_music.mp3                 │  │
│  ├── subtitles/subtitles.json                   │  │
│  └── branding/logo_transparent.png              │  │
│                                                  │
│  Outputs:                                        │
│  └── remotion_output.mp4 (or rendered.mp4)      │  │
└──────────────────────────────────────────────────┘
```

**Key classes:** `VideoRenderer` in `src/stages/render.py`, `RemotionRenderer` in `src/stages/remotion_renderer.py`

## Key Classes and Methods

### VideoRenderer (`src/stages/render.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `run()` | `run(job_id: str, video_mode: VideoMode) → VideoRenderResult` | Render video with FFmpeg |

### RemotionRenderer (`src/stages/remotion_renderer.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `run()` | `run() → dict` | Render video with Remotion |

Both renderers are instantiated and called from the `render()` CLI command in `main.py`.

## Data Flow (FFmpeg Renderer)

1. **Input assets**: Load images, narration audio, background music, subtitles from job directories
2. **FFmpeg command**: Build ffmpeg command with all inputs
3. **Render**: Execute ffmpeg (single-pass, no pre-processing)
4. **Output**: Video saved to `output/jobs/{job_id}/rendered.mp4`
5. **Thumbnail**: Generated via ffmpeg frame extraction

## Data Flow (Remotion Renderer)

1. **Setup**: Create `RemotionRenderer` with `job_id`, `frontend_dir`, `width`, `height`, `fps`, `mode`, `platform`
2. **Asset copy**: `_copy_assets_to_public()` copies images, audio, subtitles, branding to `frontend/public/`
3. **Data load**: `_load_scenes()` reads `scenes.json`, `_load_subtitles()` reads `subtitles.json`
4. **Audio path**: `_get_audio_path()` finds narration audio, `_get_background_music_path()` finds background music
5. **Props generation**: `_generate_props()` builds the props JSON with:
   - Scene data (timing, image paths, narration, text overlay, animation style)
   - Subtitle data (timing, text, word-level details)
   - Metadata (title, channel name, channel description)
   - Audio sources (narration, background music)
   - Platform/mode settings
6. **Props save**: `props.json` written to `frontend/public/props.json`
7. **Render execution**: `npx remotion render` with composition ID:
   - `StoicLandscape` for landscape mode
   - `StoicPortrait` for portrait mode
8. **Output**: Video saved to `output/jobs/{job_id}/remotion_output.mp4`
9. **DB update**: `db.update_job(job_id, status="render_complete", video_path=...)`
10. **Media explorer publish**: the subsequent `metadata` command copies the MP4 to `output/social_public/{job_id}/`, writes `index.html`, and refreshes `output/social_public/videos.html` for `stoicmodernized.zweb.ca` / `media.zweb.ca` browsing.

## Business Rules

- **Two renderers**: `--renderer-type` selects `"ffmpeg"` or `"remotion"` (default: `"remotion"`)
- **Dual render**: `render()` can produce both landscape and portrait in a single run (runs both renderers)
- **Platform**: Remotion supports `"youtube"` and `"tiktok"` platforms (determines aspect ratio and layout)
- **Mode**: `"landscape"` (1920×1080) or `"portrait"` (1080×1920)
- **Timing scale**: Remotion calculates a timing scale factor based on subtitle vs scene duration mismatch
- **Background music**: Mixed at `settings.background_music_volume` (8%) during rendering
- **Watermark**: Channel logo (`logo_transparent.png`) overlaid on video
- **Mock mode**: When `mock=True`, skips actual rendering and returns mock result
- **Timeout**: Remotion render has a 30-minute timeout

## Cross-Package References

- **005 TTS Generation** — Narration audio is input
- **006 Image Generation** — Scene images are input
- **007 Background Music** — Background music is mixed
- **008 Subtitle Generation** — Subtitle data drives on-screen text
- **010 YouTube Upload** — Rendered video is uploaded

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.video_fps` | int | `30` | Both renderers |
| `settings.video_width` | int | `1920` | Landscape mode |
| `settings.video_height` | int | `1080` | Landscape mode |
| `settings.short_video_width` | int | `1080` | Portrait mode |
| `settings.short_video_height` | int | `1920` | Portrait mode |
| `settings.background_music_volume` | float | `0.08` | Music mixing level |
| `settings.watermark_logo_path` | Path | `media/logo_transparent.png` | Logo overlay |
| `settings.watermark_scale_width` | int | `240` | Logo width |
| `settings.watermark_padding` | int | `36` | Logo padding from edge |
| `settings.mock_mode` | bool | `False` | Mock mode gate |

## Integration Points

| External | Integration |
|----------|-------------|
| FFmpeg | FFmpeg renderer (command-line tool) |
| Node.js / Remotion | Remotion renderer (`npx remotion render`) |
| React/TypeScript frontend | Remotion composition files in `frontend/src/remotion/` |
| SQLite | Persist job state |

## Non-Functional Requirements

- **Render quality**: Remotion produces higher quality with effects (transitions, zoom, pan)
- **Render speed**: FFmpeg is faster (single-pass); Remotion is slower (React rendering)
- **Timeout**: Remotion has a 30-minute max render time
- **Dual mode**: Can render both landscape and portrait in one pipeline run
- **File paths**: Remotion uses relative paths for `staticFile()` — all assets must be in `frontend/public/`
