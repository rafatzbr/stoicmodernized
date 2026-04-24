# EXTENDING.md — Decision Trees & File Modification Map

> **Baseline commit:** `d90a569a932f8f790c23469d0f6211c87c8a0878`

## 1. Decision Trees

### 1.1 How to Add a New Pipeline Stage

A "pipeline stage" is a self-contained operation (like research, script, or TTS) that runs on a job, produces artifacts, and updates the job status.

```
I need a new pipeline stage
├── Step 1: Create the stage class
│   ├── File: src/stages/<new_stage_name>.py
│   └── Class: <NewStageName>
│       └── __init__(self, job_id: str, mock: bool = False, ...)
│       └── async run(self, *args) → returns result object
│       └── save_<artifact>(self, result) → returns Path
├── Step 2: Define Pydantic models for the data
│   ├── File: src/models.py
│   └── Add one or more models (e.g., NewStageResult)
├── Step 3: Add CLI command
│   ├── File: src/main.py
│   └── Add @app.command() def <stage_name>(...) → calls stage.run() and updates db
├── Step 4: Add to retry stage_map
│   ├── File: src/main.py, in retry() function
│   └── Add "<new_stage_name>: lambda: <new_stage_name>(job_id=job_id, mock=mock)"
├── Step 5: Add to run() pipeline ordering
│   ├── File: src/main.py, in run() function
│   └── Insert stage call at the correct position in the pipeline sequence
├── Step 6: Add job record fields (if needed)
│   ├── File: src/models.py, Job class
│   └── Add path fields like <artifact>_path: Optional[str] = None
├── Step 7: Update database migration (if new Job fields)
│   ├── File: src/database.py
│   └── Add column to Job table and handle backfill
├── Step 8: Write feature spec
│   ├── File: src/ai-specs/features/NNN_<stage_name>.md
│   └── Follow the template in this document
└── Step 9: Update AI_NAVIGATION_INDEX.md
    ├── File: src/ai-specs/AI_NAVIGATION_INDEX.md
    └── Add entry to all lookup tables
```

**Why this pattern:** Every existing stage follows this exact structure. The `job_id` is the common key, mock mode is optional but always supported, and `save_*` methods persist JSON artifacts to `output/jobs/{job_id}/{stage}/`.

### 1.2 How to Add a New TTS Provider

```
I need a new TTS provider
├── Step 1: Add enum value
│   └── File: src/config.py → TTSProvider enum
├── Step 2: Add provider-specific config fields
│   └── File: src/config.py → Settings class
│       └── e.g., new_provider_api_key, new_provider_voice, etc.
├── Step 3: Create provider class in TTSStage
│   └── File: src/stages/tts.py
│       └── Add new method like _run_new_provider()
│       └── Wire into _dispatch_tts() method
├── Step 4: Test with --provider flag
│   └── python -m src.main tts <job_id> --provider newprovider
└── Step 5: Write feature spec
    └── File: src/ai-specs/features/005_tts_generation.md (update existing)
```

**Why this pattern:** TTS uses a single `TTSStage` class with a `_dispatch_tts()` method that selects the implementation based on `settings.tts_provider`. Each provider is a method on that class.

### 1.3 How to Add a New Image Generation Provider

```
I need a new image generation provider
├── Step 1: Add enum value
│   └── File: src/config.py → ImageProvider enum
├── Step 2: Add provider-specific config
│   └── File: src/config.py → Settings class
├── Step 3: Add method to ImageGenerationStage
│   └── File: src/stages/images.py
│       └── Add _run_<provider>() method
│       └── Wire into the provider selection logic
├── Step 4: Test with --mock to skip provider
│   └── python -m src.main images <job_id> --mock
└── Step 5: Update feature spec
    └── File: src/ai-specs/features/006_image_generation.md
```

### 1.4 How to Change Video Rendering

```
I need to change video rendering
├── Determine which renderer
│   ├── FFmpeg (simple, single-pass) → src/stages/render.py
│   └── Remotion (production, composable) → src/stages/remotion_renderer.py
├── FFmpeg path
│   ├── Edit VideoRenderer class
│   ├── Input assets: images/{job_id}/, audio/{job_id}/, subtitles/{job_id}/
│   └── Output: {job_id}/rendered.mp4
├── Remotion path
│   ├── Edit RemotionRenderer class
│   ├── Copy assets to frontend/public/
│   ├── Generate props.json
│   └── Run: npx remotion render
├── Wire into render() command in main.py
│   └── Add renderer_type parameter to control which path
└── Update feature spec
    └── File: src/ai-specs/features/009_video_rendering.md
```

### 1.5 How to Change the Channel Template (Stoic Modernized / AI Signal)

```
I need to change channel-specific settings
├── Step 1: Edit Settings class
│   └── File: src/config.py
│       └── channel_name, channel_voice, channel_description
├── Step 2: Check default_channel
│   └── File: src/config.py → default_channel: Channel
│       └── Can be STOIC_MODERNIZED or AI_SIGNAL
├── Step 3: Verify stages use settings
│   └── Check that script.py, scenes.py, and upload.py reference settings.channel_name etc.
└── Step 4: Test with a real run
    └── python -m src.main run --channel ai-signal <topic>
```

## 2. File Modification Map

> "When modifying X, also update Y" relationships.

| When modifying... | Also update... | Why |
|---|---|---|
| `src/models.py` (add/remove fields) | `src/database.py` (add columns) | DB schema must match model |
| `src/models.py` (add Job fields) | `src/database.py` (add columns + migration) | SQLite migration in `_migrate_jobs_table` |
| Any stage `*.py` | `src/main.py` (add CLI command) | Each stage needs a CLI entry point |
| Any stage `*.py` (add error type) | `src/main.py` (catch new exception) | Errors must be caught and update job status |
| `src/config.py` (new setting) | Feature spec for that feature | Specs must document all config keys |
| `src/config.py` (add enum value) | Any stage that references the enum | Enum changes propagate to selection logic |
| `src/stages/render.py` | `src/stages/remotion_renderer.py` (or vice versa) | Both renderers share input asset assumptions |
| `src/main.py` (pipeline order) | `src/ai-specs/features/001_pipeline_cli.md` | Spec must reflect actual execution order |
| `src/main.py` (retry stage_map) | Feature spec for the stage | Retry must be supported for all stages |
| `src/stages/tts.py` (new provider) | `src/ai-specs/features/005_tts_generation.md` | Provider details go in the spec |
| `src/stages/images.py` (new provider) | `src/ai-specs/features/006_image_generation.md` | Provider details go in the spec |
| `src/stages/upload.py` | YouTube API credentials in config | Upload depends on youtube_api_key and credentials |
| `src/database.py` (schema changes) | `src/models.py` (Job model) | Bidirectional: model ↔ DB |
| `src/logging_config.py` | Job lifecycle code | `JobLogger` is initialized per-job in each command |
| `src/utils.py` (new utility) | `ai-specs/features/013_cross_cutting.md` | Utilities are cross-cutting |

## 3. Recurring Patterns Summary

These patterns appear 2+ times across the codebase and should guide any new code:

| Pattern | Where It Appears | Description |
|---------|-----------------|-------------|
| Stage class with `run()` + `save_*()` | All 10 stages | Each stage has `async run()` and a `save_*()` method returning `Path` |
| Mock mode gate | All stages + main.py | `mock or settings.mock_mode` checked in every stage |
| JSON artifact per stage | All stages | Each stage writes output to `output/jobs/{job_id}/{stage}/` |
| DB status update after stage | All stages | `db.update_job(job_id, status="*_complete", ...)` |
| Typer CLI command per stage | `src/main.py` | Every stage is a `@app.command()` |
| Pydantic models in `models.py` | All data | Domain objects are Pydantic `BaseModel` subclasses |
| JobLogger per command | `research`, `script`, `scene`, `tts`, `render` | Each stage command initializes `JobLogger(job_id)` |
| TeeTextIO output capture | `src/main.py` | All stage commands capture stdout/stderr to job log file |
| Error catch → update_job(failed) | script, render, upload | Stage errors are caught, logged, and job status set to `failed` |
| Asset copying to frontend/public | RemotionRenderer | Images, audio, subtitles, branding all copied before render |
