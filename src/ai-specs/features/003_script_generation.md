# 003 — Script Generation

## Overview

The script generation stage transforms research results into a structured video script. It produces a title, hook, narration body, chapters, and a call-to-action (CTA). It supports both "long" mode (standard length, ~9 minutes) and "short" mode (condensed for vertical/shorts format).

## Architecture

```
┌──────────────────────────────────────────────────┐
│              ScriptStage                         │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │  async run(research_data: dict)            │  │
│  │  → LLM call for script generation          │  │
│  │  → fallback to mock if fails               │  │
│  └────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────┐  │
│  │  save_script(script: Script) → Path        │  │
│  │  → writes script.json to job directory     │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**Key class:** `ScriptStage` in `src/stages/script.py`

## Key Classes and Methods

### ScriptStage (`src/stages/script.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `run()` | `async run(research_data: dict) → Script` | Generate script via LLM |
| `save_script()` | `save_script(script: Script) → Path` | Persist JSON artifact |

### Script (`src/models.py`)

| Field | Type | Description |
|-------|------|-------------|
| `title` | `str` | Video title |
| `hook` | `str` | Opening hook/grabber |
| `narration` | `str` | Full narration text |
| `chapters` | `list[Chapter]` | Chapter markers |
| `cta` | `str` | Call-to-action |
| `short_version` | `str` | Condensed version (short mode only) |
| `generated_at` | `datetime` | Generation timestamp |

### Chapter (`src/models.py`)

| Field | Type | Description |
|-------|------|-------------|
| `title` | `str` | Chapter title |
| `timestamp` | `float` | Start time in seconds |

## Data Flow

1. **Input**: `ResearchResult` from research stage (loaded from `research.json`)
2. **Council workflow**: Research data first becomes a Whiskers brief, then a Ledger strategy pass can inject recent channel analytics guidance into packaging and script planning
3. **LLM Prompt**: Research data + council guidance → LLM generates structured script
4. **Fallback**: If local LLM fails, falls back to mock data
5. **Validation**: Script is validated against the `Script` Pydantic model
6. **Output**: `script.json` saved to `output/jobs/{job_id}/script/`
7. **DB update**: `db.update_job(job_id, status="script_complete", script_path=..., error_message=None)`

## Business Rules

- **Script generation error**: If LLM call fails, `ScriptGenerationError` is raised. The stage does NOT fail silently — it saves a `script_generation_report.json` with details.
- **Error reporting**: Failed runs produce `script_generation_report.json` in the script directory with fields: `local_llm_success`, `script_generation_succeeded`, `failure_reason`.
- **Council analytics guidance**: For Stoic Modernized council runs, the script stage may read the latest saved workspace analytics artifacts and feed them into a Ledger strategy pass before drafting/title packaging.
- **Graceful degradation**: If no analytics artifacts exist, Ledger receives an explicit "no saved analytics artifacts" context and the rest of the council workflow still runs.
- **Two output modes**: 
  - `VideoMode.LONG`: Full narration with detailed chapters
  - `VideoMode.SHORT`: Condensed narration for vertical/shorts format
- **Title consistency**: Title from research is preserved and used across stages.
- **Recent-script variety**: Short script prompts include recent titles/hooks as negative examples. Generated shorts are rejected before scene planning when they repeat an opener pattern used by at least two recent scripts (for example repeated `Your boss ...` starts), when title/hook/narration terms are too similar to a recent script, or when the script repeats a recent retry artifact that never reached metadata/upload packaging.

## Cross-Package References

- **002 Research Stage** — Input is `ResearchResult` from research
- **004 Scene Planning** — Output `Script` is input to scene planning
- **011 Configuration** — Channel voice, model settings affect script generation

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.channel_name` | str | `"Stoic Modernized"` | Script template |
| `settings.channel_voice` | str | `"calm, practical..."` | Script tone |
| `settings.ai_signal_channel_name` | str | `"The AI Signal"` | AI Signal channel scripts |
| `settings.ai_signal_channel_voice` | str | `"urgent, precise..."` | AI Signal scripts |
| `settings.local_script_model` | str | `None` | LLM model override |
| `settings.local_script_max_tokens` | int | `1800` | LLM token limit |
| `settings.local_script_temperature` | float | `0.7` | LLM temperature |
| `settings.local_script_min_section_words` | int | `8` | Minimum words per section |
| `settings.local_llm_base_url` | str | `"http://localhost:8080/v1/chat/completions"` | LLM endpoint |
| `settings.local_llm_timeout_seconds` | float | `120.0` | LLM timeout |
| `settings.mock_mode` | bool | `False` | Mock mode gate |

## Integration Points

| External | Integration |
|----------|-------------|
| Local LLM (Ollama/OpenAI-compatible API) | Script generation via `local_llm_base_url` |
| SQLite | Persist job state |

## Non-Functional Requirements

- **Timeout**: LLM calls timeout after 120 seconds (configurable).
- **Error handling**: Script generation errors are non-fatal — they produce a report and set job status to `script_failed`.
- **Token limits**: Max 1800 tokens for script generation (configurable per model override).
