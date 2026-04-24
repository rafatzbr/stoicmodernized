# AGENTS.md — Stoic Modernized Agent Guide

> **Baseline commit:** `d90a569a932f8f790c23469d0f6211c87c8a0878`

## Guardrails

- **Never run destructive commands** (rm -rf, truncate, drop table) without explicit user approval.
- **Never push changes** to the remote repository without asking.
- **Never modify `.env`** with real API keys — use environment variables or `.env.local` for secrets.
- **Mock mode is your friend**: Use `--mock` flag when testing to avoid calling external APIs.
- **Pipeline order matters**: Stages must run in order — research → script → scene → tts → images → music → subtitles → render → metadata → upload.
- **SQLite is single-writer**: The pipeline is sequential — no concurrent database writes.
- **Remotion requires Node.js**: The Remotion renderer needs `npx remotion` available in PATH.
- **YouTube upload requires OAuth2**: Credentials must be set up before upload will work.

## Mandatory Reading Order

1. **AI_NAVIGATION_INDEX.md** — Find the feature number you need
2. **Feature spec** (`ai-specs/features/NNN__name.md`) — Understand the feature
3. **EXTENDING.md** — Follow the decision trees and patterns
4. **Source code** — Search code for symbol lookups and implementation details

## Feature Quick Reference

| Topic | Feature # | Spec File |
|-------|-----------|-----------|
| Pipeline CLI & Job Lifecycle | 001 | `ai-specs/features/001_pipeline_cli.md` |
| Research Stage | 002 | `ai-specs/features/002_research_stage.md` |
| Script Generation | 003 | `ai-specs/features/003_script_generation.md` |
| Scene Planning | 004 | `ai-specs/features/004_scene_planning.md` |
| TTS Generation | 005 | `ai-specs/features/005_tts_generation.md` |
| Image Generation | 006 | `ai-specs/features/006_image_generation.md` |
| Background Music | 007 | `ai-specs/features/007_background_music.md` |
| Subtitle Generation | 008 | `ai-specs/features/008_subtitle_generation.md` |
| Video Rendering | 009 | `ai-specs/features/009_video_rendering.md` |
| YouTube Upload | 010 | `ai-specs/features/010_youtube_upload.md` |
| Configuration & Channels | 011 | `ai-specs/features/011_configuration.md` |
| Persistence Layer | 012 | `ai-specs/features/012_persistence.md` |
| Cross-Cutting Concerns | 013 | `ai-specs/features/013_cross_cutting.md` |

## Package Structure

| Package | Role | Build Dependency |
|---------|------|-----------------|
| `src/` | Service Host (CLI, stages, config, models, db) | None (self-contained) |
| `frontend/` | Remotion rendering frontend (React/TypeScript) | `src/` must produce artifacts |
| `tests/` | Test suite | None |

## Pre-commit Checklist

- [ ] Tests pass (if any exist)
- [ ] Feature spec updated if behavior changed
- [ ] No secrets/PII in logs or code
- [ ] Build succeeds (`pip install -e .`)
- [ ] Mock mode still works (`--mock` flag on a stage)
