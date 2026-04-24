# 006 — Image Generation

## Overview

The image generation stage creates visual assets for each video scene. It supports multiple providers: `sd_cli` (stable diffusion CLI), `sd_server` (stable diffusion web UI / ComfyUI), `dall_e` (OpenAI DALL-E). Each scene gets a unique image based on a visual prompt from the scene plan.

## Architecture

```
┌──────────────────────────────────────────────────┐
│           ImageGenerationStage                   │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  async run(scene_plan: dict)               │  │
│  │  → for each scene:                         │  │
│  │    - build prompt from visual_prompt       │  │
│  │  → dispatch to provider                    │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  save_image_assets(...) → List[Path]       │  │
│  │  → saves to output/jobs/{job_id}/images/   │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  Providers (selected by type):             │  │
│  │  - ImageSDCLI    (local, stable-diffusion) │  │
│  │  - ImageSDServer (local/remote web UI)     │  │
│  │  - ImageDALL_E   (OpenAI API)              │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**Key class:** `ImageGenerationStage` in `src/stages/images.py`

## Key Classes and Methods

### ImageGenerationStage (`src/stages/images.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `run()` | `async run(scene_plan: dict) → List[Path]` | Generate images for all scenes |
| `save_image_assets()` | `save_image_assets(assets)` | Persist asset metadata |

### Provider Classes

| Class | Provider Enum | Description |
|-------|--------------|-------------|
| `ImageSDCLI` | `ImageProvider.SD_CLI` | Local stable diffusion via CLI |
| `ImageSDServer` | `ImageProvider.SD_SERVER` | SD WebUI / ComfyUI via API |
| `ImageDALLE` | `ImageProvider.DALL_E` | OpenAI DALL-E API |

## Data Flow

1. **Input**: `ScenePlan` with `Scene.visual_prompt` for each scene
2. **Prompt assembly**: Base prompt + scene-specific visual prompt
3. **Provider dispatch**: Select provider based on `settings.image_provider` (note: this setting is NOT defined in config — it uses a hardcoded fallback to `sd_cli`)
4. **Generation**: Each scene generates one image: `scene_XXX.jpg`
5. **Seeding**: Persistent seed management per scene for reproducibility
6. **Output**: Images saved to `output/jobs/{job_id}/images/` as `scene_001.jpg`, `scene_002.jpg`, etc.
7. **DB update**: `db.update_job(job_id, status="images_complete", images_dir=...)`

## Business Rules

- **Static prompt fragments**: The module includes predefined fragments (`PROFESSIONS`, `ACTIONS`, `LOCATIONS`, etc.) that are combined with scene-specific prompts.
- **Scene mode cycling**: `_get_scene_mode()` cycles through different scene modes (e.g., professional, outdoor, abstract) to create visual variety.
- **Seed persistence**: Seeds are stored per scene for reproducibility — `_get_prompt_seed()` checks for existing seeds before generating new ones.
- **Mode instructions**: `_mode_instruction()` injects mode-specific guidance into prompts.
- **Placeholder mode**: If `force_placeholder_images` is True, skips actual generation and creates placeholder images.
- **Error handling**: `ImageGenerationError` is raised for provider failures.

## Cross-Package References

- **004 Scene Planning** — Input is `Scene` list with visual prompts
- **009 Video Rendering** — Generated images are input to FFmpeg/Remotion rendering

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.sd_cli_path` | str | `"/home/rafatz/dev/stable-diffusion.cpp/build/bin/sd-cli"` | SD CLI provider |
| `settings.sd_model_path` | str | `"/data/sd-models/sd3.5_large.safetensors"` | SD model |
| `settings.sd_clip_l_path` | str | `"/data/sd-models/clip_l.safetensors"` | SD CLIP |
| `settings.sd_clip_g_path` | str | `"/data/sd-models/clip_g.safetensors"` | SD CLIP |
| `settings.sd_t5xxl_path` | str | `"/data/sd-models/t5xxl_fp16.safetensors"` | SD T5 |
| `settings.sd_image_width` | int | `544` | Image width |
| `settings.sd_image_height` | int | `960` | Image height |
| `settings.sd_cfg_scale` | float | `3.8` | CFG scale (lower = more natural) |
| `settings.sd_steps` | int | `20` | Denoising steps |
| `settings.sd_sampling_method` | str | `"euler"` | Sampling method |
| `settings.sd_negative_prompt` | str | `"blurry, low quality..."` | Negative prompt |
| `settings.force_placeholder_images` | bool | `False` | Skip real generation |
| `settings.sd_server_url` | str | `"http://localhost:1234"` | SD Server URL |
| `settings.sd_server_api_path` | str | `"/sdapi/v1/txt2img"` | SD Server API |
| `settings.sd_server_timeout_seconds` | float | `300.0` | SD Server timeout |
| `settings.mock_mode` | bool | `False` | Mock mode gate |

## Integration Points

| External | Integration |
|----------|-------------|
| stable-diffusion.cpp CLI | Local image generation |
| SD WebUI / ComfyUI API | Remote/local SD server |
| OpenAI DALL-E API | Cloud image generation |
| SQLite | Persist job state |

## Non-Functional Requirements

- **CFG scale**: Set to 3.8 (per Rafael's note: "Lower for more natural results (3.5-4.0 range)").
- **Image dimensions**: 544×960 (portrait aspect ratio, compatible with 1080×1920 video).
- **Timeout**: SD Server API calls timeout after 300 seconds.
- **Reproducibility**: Seed persistence enables scene regeneration with identical visuals.
