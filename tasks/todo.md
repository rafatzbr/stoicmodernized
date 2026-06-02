# Task: Fix initial duplicate-subject guardrails

## Plan
- [x] Inspect current topic/script duplicate guardrail implementation and recent job artifacts.
- [x] Patch early validation so script-only/research-only recent attempts are considered, not only jobs with metadata.
- [x] Add regression coverage for the coworker-disrespect / coworker-steals-credit repeat and script-only prior artifacts.
- [x] Run targeted tests and compile checks.
- [x] Update lessons for this correction and report results.

## Review
- Root cause: initial research/script subject guardrails scanned packaged `metadata.json` jobs only. Retry artifacts that had `script.json` or `research.json` but no metadata were invisible, so a later candidate could repeat the same subject family before media spend.
- Fix: `YouTubeUploader` now scans one best subject artifact per recent job: metadata first, then script, then research.
- Fix: stale-scan cutoff now counts only artifacts outside the current month and outside the rolling recent-subject window, so last-week script-only retries are not skipped.
- Fix: `react` is a trigger token, catching coworker/react conflict repeats such as coworker steals credit vs coworker disrespect.
- Added regression tests for both research-time and script-time blocking of script-only retry repeats.
- Verification passed: `tests/test_upload_metadata.py`, `tests/test_daily_video_orchestrator.py`, `py_compile`, and daily `--check`.
