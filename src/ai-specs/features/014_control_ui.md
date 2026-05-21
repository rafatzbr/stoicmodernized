# 014 — Control UI

## Overview

The control UI is the local operations surface for the Stoic Modernized pipeline. It is split across:

- `frontend/` — Vite + React + TypeScript dashboard
- `src/ui_api.py` — FastAPI backend for jobs, runs, config editing, uploads, and topic suggestion

The current UI supports both channel families:

- `stoic-modernized`
- `ai-signal`

It is intentionally dark-mode-first and uses a Nothing-inspired visual system: monochrome hierarchy, large primary state, minimal ornament, and mono labels.

## Key Files

| File | Role |
|---|---|
| `frontend/src/main.tsx` | MUI theme, font stack, global dark UI styling |
| `frontend/src/pages/DashboardPage.tsx` | Main control surface orchestration |
| `frontend/src/components/RunControls.tsx` | Full-run controls, channel selection, topic suggestion |
| `frontend/src/components/StepRunner.tsx` | Partial rerun controls |
| `frontend/src/components/JobsList.tsx` | Job selection and deletion |
| `frontend/src/components/LiveLogs.tsx` | Active run log viewer |
| `frontend/src/components/JobAssets.tsx` | Asset inspection, rerun shortcuts, upload selection |
| `frontend/src/components/FileEditors.tsx` | Inline `.env` and `src/config.py` editing |
| `src/ui_api.py` | FastAPI endpoints backing the dashboard |

## Backend API Surface

### Jobs

- `GET /api/jobs` — list jobs plus channel metadata from `output/jobs/<job_id>/job.json`
- `GET /api/jobs/{job_id}` — detailed job info + discovered assets + channel context
- `DELETE /api/jobs/{job_id}` — delete job directory and DB row
- `GET /api/jobs/{job_id}/assets/{asset_path}` — serve a job asset
- `POST /api/jobs/{job_id}/upload` — upload a selected rendered video asset

### Runs

- `POST /api/runs` — start full pipeline run
- `POST /api/runs/steps` — start selected stage sequence
- `GET /api/runs/{run_id}` — fetch live run state/log tail
- `POST /api/runs/{run_id}/stop` — stop the active subprocess

### Config + Utilities

- `GET /api/config/env` / `POST /api/config/env`
- `GET /api/config/file` / `POST /api/config/file`
- `POST /api/topics/suggest`

## Channel Handling

The UI passes `channel` through to full runs, step runs, and topic suggestion. The backend forwards `--channel <value>` to `src.main` stage commands.

For existing jobs, UI display channel metadata is derived from the persisted per-job `job.json` context rather than the SQLite schema.

## Topic Suggestion Rules

Topic suggestion is channel-aware:

- Stoic Modernized → practical Stoic/workplace topic suggestions
- The AI Signal → timely AI-news rundown topics

The suggestion endpoint now returns an explicit error payload when the local model fails. It does not silently invent a fallback topic.

## UX Structure

The dashboard uses a three-zone layout:

1. **Hero state** — single dominant system status (`READY`, `RUNNING`, etc.)
2. **Left rail** — run creation, partial runs, job selection
3. **Main rail** — live logs, job inspector, config editors

The UI avoids heavy color use and relies on:

- large primary text for current state
- Space Grotesk for headings/body
- Space Mono for labels, buttons, metadata
- monochrome surfaces with a single red interrupt color

## Behavior Notes

- The dashboard polls active runs every 1.5 seconds while `runId` is set.
- Completing a run refreshes the jobs list and current job detail.
- Job deletion removes both on-disk files and the DB row through the API.
- Upload selection is asset-based, not hardcoded to a single render filename.
- Config editors write directly to project files; there is no draft layer.

## Development Workflow

For hot reload during UI development, use:

```bash
./scripts/ui-dev.sh
```

This activates the repo `.venv` and starts:

- `uvicorn src.ui_api:app --reload` for backend auto-reload
- `npm run dev` in `frontend/` for Vite HMR

The Vite app talks to the backend via `VITE_API_BASE_URL` set by the launcher.

## Non-Functional Notes

- The UI is local-ops oriented, not user-facing product UI.
- The theme is intentionally flat: no glassmorphism, no gradients, no decorative shadows.
- Dark mode is the implemented/default mode for the current design system.
