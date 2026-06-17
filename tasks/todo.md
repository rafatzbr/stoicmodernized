# Guardrail/topic freshness fix plan

## Objective

Fix daily Stoic Modernized topic selection so it preserves strict duplicate protection while allowing distinct modern-work topics, including coworker-relations grievances with different sentiment handling.

## Tasks

- [ ] Add regression tests first:
  - specificity accepts access/shared-drive, failed import, noisy workspace, and coworker-relations mechanisms.
  - same-month guardrail ignores soft emotional overlap alone (`anxiety`, `react`, `fear`, etc.).
  - exact duplicate/recent-title guardrail remains strict.
  - daily orchestrator fallback skips recent/rejected stale titles and includes coworker-relations lane.
- [ ] Implement project guardrail changes:
  - split hard concrete trigger signals from soft sentiment signals.
  - add coworker-relations hard triggers and grievance/sentiment terms.
  - align research specificity whitelist with prompt examples.
- [ ] Implement daily orchestrator changes:
  - build recent topic/failure blocklist from project DB.
  - pass recent blocked topics into Whiskers prompts.
  - replace stale static fallback behavior with lane-aware candidates and skip recent/rejected titles.
- [x] Verify:
  - targeted pytest files.
  - full pytest suite.
  - py_compile daily orchestrator and touched project stages.
  - confirmed daily orchestrator has no safe `--check` flag, so did not run the cron script with guessed args.

## Review notes

Implemented and verified. Full suite: `uv run python -m pytest` → 252 passed.
