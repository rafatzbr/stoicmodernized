# AI Navigation Index — Stoic Modernized

> **Last updated:** 2026-04-24
> **Baseline commit:** `d90a569a932f8f790c23469d0f6211c87c8a0878`

## How to Use

1. Read this index to find the feature number you need
2. Open the corresponding feature spec: `src/ai-specs/features/NNN__name.md`
3. Consult `EXTENDING.md` for decision trees and file modification patterns
4. Read `AGENTS.md` first for guardrails and reading order

## In-Progress Features

None. All documented features are implemented in the codebase.

## Features

### Feature Numbers → File Paths

| # | Feature | Path |
|---|---------|------|
| 001 | Pipeline CLI & Job Lifecycle | `src/ai-specs/features/001_pipeline_cli.md` |
| 002 | Research Stage | `src/ai-specs/features/002_research_stage.md` |
| 003 | Script Generation | `src/ai-specs/features/003_script_generation.md` |
| 004 | Scene Planning | `src/ai-specs/features/004_scene_planning.md` |
| 005 | TTS Generation | `src/ai-specs/features/005_tts_generation.md` |
| 006 | Image Generation | `src/ai-specs/features/006_image_generation.md` |
| 007 | Background Music | `src/ai-specs/features/007_background_music.md` |
| 008 | Subtitle Generation | `src/ai-specs/features/008_subtitle_generation.md` |
| 009 | Video Rendering | `src/ai-specs/features/009_video_rendering.md` |
| 010 | YouTube Upload | `src/ai-specs/features/010_youtube_upload.md` |
| 011 | Configuration & Channel Selection | `src/ai-specs/features/011_configuration.md` |
| 012 | Persistence Layer | `src/ai-specs/features/012_persistence.md` |
| 013 | Cross-Cutting Concerns | `src/ai-specs/features/013_cross_cutting.md` |
| 014 | Control UI | `src/ai-specs/features/014_control_ui.md` |
| 015 | Social Distribution | `src/ai-specs/features/015_social_distribution.md` |

## Feature Quick Lookup

| Feature | Key Files | Keywords |
|---------|-----------|----------|
| 001 Pipeline CLI | `src/main.py` | `run`, `render`, `retry`, `jobs`, `idea` |
| 002 Research | `src/stages/research.py` | `research`, `sources`, `insights` |
| 003 Script | `src/stages/script.py` | `script`, `narration`, `chapters`, `hook` |
| 004 Scenes | `src/stages/scenes.py` | `scenes`, `scene_plan`, `visual_prompt` |
| 005 TTS | `src/stages/tts.py` | `tts`, `edge`, `edge-tts` |
| 006 Images | `src/stages/images.py` | `images`, `sd_cli`, `stable diffusion`, `dall_e` |
| 007 Music | `src/stages/music.py` | `music`, `background`, `youtube` |
| 008 Subtitles | `src/stages/subtitles.py` | `subtitles`, `whisper`, `asr` |
| 009 Rendering | `src/stages/render.py`, `remotion_renderer.py` | `render`, `ffmpeg`, `remotion` |
| 010 Upload | `src/stages/upload.py` | `upload`, `youtube`, `API`, `publish` |
| 011 Config | `src/config.py` | `settings`, `channel`, `video_mode`, `provider` |
| 012 Persistence | `src/database.py`, `src/models.py` | `job`, `db`, `SQLAlchemy`, `sqlite` |
| 013 Cross-cutting | `src/utils.py`, `src/logging_config.py` | `utils`, `mock_mode`, `logging`, `TeeTextIO` |
| 014 Control UI | `frontend/src/`, `src/ui_api.py` | `dashboard`, `ui`, `jobs`, `runs`, `config editor` |
| 015 Social Distribution | `src/stages/social_distribution.py` | `distribute`, `tiktok`, `instagram`, `facebook`, `reels` |

## Code Location Map

| Pattern | File → Feature |
|---------|----------------|
| `src/main.py` | CLI entry point → 001 |
| `src/stages/research.py` | → 002 |
| `src/stages/script.py` | → 003 |
| `src/stages/scenes.py` | → 004 |
| `src/stages/tts.py` | → 005 |
| `src/stages/images.py` | → 006 |
| `src/stages/music.py` | → 007 |
| `src/stages/subtitles.py` | → 008 |
| `src/stages/render.py` | → 009 |
| `src/stages/remotion_renderer.py` | → 009 |
| `src/stages/upload.py` | → 010 |
| `src/config.py` | → 011 |
| `src/database.py` | → 012 |
| `src/models.py` | → 012 |
| `src/utils.py` | → 013 |
| `src/logging_config.py` | → 013 |
| `src/ui_api.py` | → 014 |
| `frontend/src/` | → 014 |
| `src/stages/social_distribution.py` | → 015 |
