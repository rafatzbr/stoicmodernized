# Errors

Command failures and integration errors.

---

## [ERR-20260424-001] news_registry_similarity

**Logged**: 2026-04-24T22:13:51.192848+00:00
**Priority**: medium
**Status**: fixed
**Area**: backend

### Summary
Smarter news dedupe failed on first run because list token collections were unioned like sets.

### Error
```
TypeError: unsupported operand type(s) for |: 'list' and 'list'
```

### Context
- Command/operation attempted: local sanity test for semantic-ish duplicate detection in `src/news_registry.py`
- The first implementation of `_story_tokens()` tried to union list outputs from `_extract_tokens()`.
- Fixed by converting token lists to sets before overlap/signature logic.

### Suggested Fix
When expanding dedupe heuristics, keep token containers as sets at the comparison boundary and retain a small headline-variant regression test.

### Metadata
- Reproducible: yes
- Related Files: src/news_registry.py

---
## [ERR-20260425-001] remotion_scene_image_index_mismatch

**Logged**: 2026-04-25T08:04:11.490664+00:00
**Priority**: high
**Status**: fixed
**Area**: backend

### Summary
Remotion render failed with 404 for /public/images/scene_009.jpg because props generation used 1-indexed scene filenames while generated images were 0-indexed.

### Details
`src/stages/remotion_renderer.py` built Remotion scene props with `enumerate(scenes, 1)`, producing `scene_001.jpg` through `scene_009.jpg`. The pipeline generated actual image assets as `scene_000.jpg` through `scene_008.jpg`, so the last scene referenced a nonexistent file and render failed with `CancelledError` / `EncodingError`.

### Resolution
Use `scene['scene_number']` directly when building `imageSrc` and `sceneNumber` in Remotion props.

### Metadata
- Source: error
- Related Files: src/stages/remotion_renderer.py
- Tags: remotion, render, indexing, images

---

## 2026-04-25 - Shell assumed `python` exists
- **Context**: While patching AI Signal script generation, I invoked `python` directly in a project where only `.venv/bin/python` is available on PATH.
- **Impact**: Patch command failed before touching files.
- **Fix**: Re-ran with `.venv/bin/python`; for this project, use `.venv/bin/python` consistently for Python one-liners and validation.

## [ERR-20260428-001] image_generation_timeout_budget

**Logged**: 2026-04-28T11:13:46-07:00
**Priority**: high
**Status**: pending
**Area**: infra

### Summary
Manual image-generation commands were killed because the external command timeout was too short for slow SD image generation.

### Details
The SD server can take up to ~10 minutes per generated image. For AI Signal jobs with 6 scenes, command timeout should be calculated from scene count instead of using a flat 10-minute timeout.

### Suggested Action
When running image generation manually, use timeout >= scene_count * 600 seconds plus overhead. For 6 images, use at least 3600 seconds.

### Metadata
- Source: command_failure,user_feedback
- Related Files: src/stages/images.py, src/main.py
- Tags: image-generation, timeout, sd-server

---

## [ERR-20260507-001] python_path_assumption

**Logged**: 2026-05-07T09:05:00-07:00
**Priority**: low
**Status**: pending
**Area**: infra

### Summary
A repo inspection command assumed `python` was on PATH, but this project expects the virtualenv interpreter.

### Error
```text
/bin/bash: line 1: python: command not found
```

### Context
- Command/operation attempted: duration audit over rendered jobs
- Environment detail: the reliable interpreter here is `./.venv/bin/python`
- The check succeeded immediately after rerunning with the virtualenv interpreter

### Suggested Fix
Prefer `./.venv/bin/python` (or verify `python3`) for project-local one-liners in this repo.

### Metadata
- Reproducible: yes
- Related Files: tasks/todo.md

---
