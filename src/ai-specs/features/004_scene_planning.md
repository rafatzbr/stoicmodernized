# 004 — Scene Planning

## Overview

The scene planning stage transforms a video script into a structured scene plan. Each scene has a start/end time, narration segment, visual prompt for image generation, optional text overlay, and animation style. The stage differentiates between short and long video modes and uses a mock planner or local LLM for scene generation.

## Architecture

```
┌──────────────────────────────────────────────────┐
│               SceneStage                         │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  async run(script_data: dict)              │  │
│  │  → parses script into timed sections       │  │
│  │  → generates scene plan (mock or LLM)      │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  save_scene_plan(plan: ScenePlan) → Path   │  │
│  │  → writes scenes.json to job directory     │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**Key class:** `SceneStage` in `src/stages/scenes.py`

## Key Classes and Methods

### SceneStage (`src/stages/scenes.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `run()` | `async run(script_data: dict) → ScenePlan` | Generate scene plan |
| `save_scene_plan()` | `save_scene_plan(plan: ScenePlan) → Path` | Persist JSON artifact |

### Scene (`src/models.py`)

| Field | Type | Description |
|-------|------|-------------|
| `scene_number` | `int` | Sequential scene number |
| `start_time` | `float` | Start time in seconds |
| `end_time` | `float` | End time in seconds |
| `narration_segment` | `str` | Portion of narration for this scene |
| `visual_prompt` | `str` | Prompt for image generation |
| `text_overlay` | `Optional[str]` | Optional on-screen text |
| `animation_style` | `str` | Animation type (default: `"zoom"`) |

### ScenePlan (`src/models.py`)

| Field | Type | Description |
|-------|------|-------------|
| `scenes` | `list[Scene]` | Scene list |
| `intro_duration` | `float` | Intro duration (default: 3.0s) |
| `outro_duration` | `float` | Outro duration (default: 5.0s) |
| `total_duration` | `float` | Computed: max scene end + intro + outro |
| `topic` | `str` | Video topic |

**Note:** `total_duration` is computed automatically via `@model_validator(mode="after")` — it equals `max(scene.end_time) + intro_duration + outro_duration`.

## Data Flow

1. **Input**: `Script` data from script stage (loaded from `script.json`)
2. **Parse**: Script narration is split into timed segments based on scene count
3. **Generate**: For each segment, a visual prompt is generated
4. **Short vs Long**: Scene count and duration constraints differ:
   - `SHORT`: ~6 scenes, max 60 seconds, portrait (1080x1920)
   - `LONG`: Variable scenes, max 900 seconds, landscape (1920x1080)
5. **Output**: `scenes.json` saved to `output/jobs/{job_id}/scenes/`
6. **DB update**: `db.update_job(job_id, status="scene_complete", scene_plan_path=...)`

## Business Rules

- **Mock planner**: Uses `_mock_scene_plan()` to generate deterministic placeholder scenes when `mock=True` or `settings.mock_mode`.
- **LLM planner**: Uses local LLM to generate scenes when `mock=False`.
- **Intro/Outro**: Always included (3s intro, 5s outro by default).
- **Scene timing**: `total_duration` is auto-computed — never manually set.
- **Scene numbering**: Scenes are 1-indexed and sequential.

## Cross-Package References

- **003 Script Generation** — Input is `Script` data from script stage
- **006 Image Generation** — Output `Scene.visual_prompt` feeds into image generation
- **005 TTS Generation** — Output `Scene.narration_segment` feeds into TTS
- **009 Video Rendering** — Output `Scene` data drives Remotion/FFmpeg rendering

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.short_target_scene_count` | int | `6` | Scene planning for short mode |
| `settings.short_max_duration_seconds` | int | `60` | Max duration for short mode |
| `settings.long_max_duration_seconds` | int | `900` | Max duration for long mode |
| `settings.local_scene_model` | str | `None` | LLM model override |
| `settings.local_scene_max_tokens` | int | `1400` | LLM token limit for scenes |
| `settings.local_scene_temperature` | float | `0.3` | LLM temperature for scenes |
| `settings.mock_mode` | bool | `False` | Mock mode gate |

## Integration Points

| External | Integration |
|----------|-------------|
| Local LLM | Scene generation (when mock=False) |
| SQLite | Persist job state |

## Non-Functional Requirements

- **Determinism**: Mock mode produces identical scenes every run.
- **Temperature**: Scene generation uses low temperature (0.3) for consistency.
- **Validation**: `ScenePlan` auto-computes `total_duration` via Pydantic model validator.
