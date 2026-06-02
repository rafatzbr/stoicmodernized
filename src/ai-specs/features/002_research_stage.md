# 002 — Research Stage

## Overview

The research stage gathers relevant source material for a given topic. It searches the web (via Brave API through the AI agent's context), collects sources with relevance scores, and produces a structured research result including key insights and workplace applications.

## Architecture

```
┌──────────────────────────────────────────────┐
│              ResearchStage                   │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  async run(topic: str)                 │  │
│  │  → performs web search                 │  │
│  │  → collects sources                    │  │
│  │  → generates insights                  │  │
│  └────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────┐  │
│  │  save_results(results) → Path          │  │
│  │  → writes research.json                │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

**Key class:** `ResearchStage` in `src/stages/research.py`

## Key Classes and Methods

### ResearchStage (`src/stages/research.py`)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `run()` | `async run(topic: str) → ResearchResult` | Fetch sources, extract insights |
| `save_results()` | `save_results(results: ResearchResult) → Path` | Write JSON to job directory |

### ResearchResult (`src/models.py`)

| Field | Type | Description |
|-------|------|-------------|
| `title` | `str` | Topic title |
| `sources` | `list[ResearchSource]` | Collected sources |
| `key_insights` | `list[str]` | Extracted insights |
| `workplace_applications` | `list[str]` | Practical workplace connections |

### ResearchSource (`src/models.py`)

| Field | Type | Description |
|-------|------|-------------|
| `title` | `str` | Source title |
| `url` | `str` | Source URL |
| `note` | `str` | Why this source is relevant |
| `relevance` | `float` (0.0–1.0) | Relevance score |
| `source` | `str` | Source name/provider |

## Data Flow

1. **Input**: `topic` string (e.g., "Stoic approaches to workplace conflict")
2. **Validate topic early**: Reject topics that are too close to recent uploads before expensive stages continue
3. **Retry with new candidate**: If the topic fails validation, rotate to the next ledger-generated topic and retry within research
4. **Search**: Web search for relevant sources
5. **Score**: Each source scored for relevance (0.0–1.0)
6. **Synthesize**: Generate key insights and workplace applications
7. **Output**: `ResearchResult` saved as JSON to `output/jobs/{job_id}/research/research.json`
8. **DB update**: `db.update_job(job_id, status="research_complete", research_path=...)`

## Business Rules

- **Mock mode**: In mock mode, returns deterministic mock data with predefined sources.
- **Topic guardrail**: Research validates the requested topic against recent uploads and recent retry artifacts (`script.json` / `research.json`) before doing expensive downstream work. If the topic is rejected, research must choose a new candidate topic before proceeding.
- **Research-stage retries**: Topic duplication and cooldown decisions are handled inside research, not deferred to upload. Abandoned script-only attempts still count as recent subject evidence so the next candidate cannot repeat the same actor/trigger family.
- **Relevance scoring**: Sources must have a relevance score between 0.0 and 1.0 (enforced by Pydantic `Field(ge=0.0, le=1.0)`).
- **Output format**: Always JSON, always under `output/jobs/{job_id}/research/`.
- **Source attribution**: Each source must include a `note` explaining its relevance.

## Cross-Package References

- **003 Script Generation** — Research results are the input to script generation
- **012 Persistence** — Results are saved as JSON and path stored in DB

## Configuration

| Config Key | Type | Default | Used By |
|------------|------|---------|---------|
| `settings.mock_mode` | bool | `False` | ResearchStage |
| `settings.jobs_dir` | Path | `output/jobs/` | ResearchStage.save_results() |

## Integration Points

| External | Integration |
|----------|-------------|
| Web search (via AI agent) | Source discovery |
| SQLite | Persist job state |

## Non-Functional Requirements

- **Determinism**: Mock mode ensures reproducible results for testing.
- **Idempotency**: Re-running research on the same topic produces similar results (in non-mock mode, this depends on web content availability).
