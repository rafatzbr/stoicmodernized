# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---
## [LRN-20260424-001] correction

**Logged**: 2026-04-24T22:54:00Z
**Priority**: medium
**Status**: pending
**Area**: docs

### Summary
When this repo is run through its local environment, provide a venv-aware launcher instead of assuming direct `python -m ...` use is the simplest path.

### Details
I initially documented `python -m src.main ui-dev` as the primary workflow. Rafael corrected that this project uses a venv and asked for a shell launcher that activates the venv and starts the dev servers. The simpler, lower-friction workflow is `./scripts/ui-dev.sh`.

### Suggested Action
Prefer repo-local launcher scripts for recurring dev workflows when a project already relies on `.venv` activation.

### Metadata
- Source: user_feedback
- Related Files: scripts/ui-dev.sh, README.md, src/ai-specs/features/014_control_ui.md
- Tags: venv, dev-workflow, ui

---

## 2026-04-25 - Correction: timestamp checks are insufficient for regenerated media
- **Category**: correction
- **Context**: User reported that subtitles, narration, and video still used the old AI Signal script even after I claimed regeneration succeeded based mostly on timestamps and render completion.
- **Learning**: For media regeneration, verify semantic content consumed by each downstream stage (TTS input, subtitles text, render props/audio path/content), not just artifact modification times or successful exit codes.

## 2026-04-25 - Correction: incomplete currency fragments must be validation failures
- **Category**: correction
- **Context**: User found latest AI Signal script line: "OpenAI is actively diversifying its cloud strategy through a $50." The script pipeline allowed an incomplete dollar amount through.
- **Learning**: AI Signal script/subtitle validation must reject dangling currency fragments like `$50.` or `$880.` and should verify generated narration against complete research facts before TTS/render.

## 2026-04-25 - Correction: short AI Signal copy must not repeat headline as fact
- **Category**: correction
- **Context**: User noted the compact 48s AI Signal script became stupid because the title and sentence repeated the same information without adding news value.
- **Learning**: Shorts compression should use headline + additive fact/context, not headline + paraphrase. Validate for semantic duplication, not only dangling facts.

## 2026-04-25 - Correction: AI Signal shorts need editorial utility, not compressed labels
- **Category**: correction
- **Context**: User flagged remaining awkward short copy: incomplete pronoun-led fact lines, generic statements that add no information, weak descriptions, and a CTA with no reason to follow.
- **Learning**: AI Signal short copy should name the actor in each fact line, add concrete context/consequence, avoid generic trend filler, and end with a reason-based CTA.

## 2026-04-26 — correction — YouTube OAuth tokens must be channel-specific

Rafael corrected an upload routed to the wrong YouTube channel. Root cause: a root-level OAuth token and a misplaced channel token allowed ambiguous credential routing. For YouTube uploads, never rely on root/default/ADC credentials. Store tokens under `~/.stoic-modernized/<channel>/oauth2_token.json`, authenticate with `--channel <channel>`, and fail explicitly if the channel-specific token is missing.

## [LRN-20260428-001] correction

**Logged**: 2026-04-28T11:13:46-07:00
**Priority**: high
**Status**: pending
**Area**: backend

### Summary
AI Signal script regeneration must not create generic "AI story X" headlines or mismatch headlines with summaries.

### Details
After removing advice-style `workplace_applications`, fallback headline generation used `AI story X` when the summary was too long for the headline candidate helper. Short-summary compression also dropped important context after commas, making the first story sound disconnected.

### Suggested Action
Generate fallback headlines from the actual summary before any generic fallback, add AI Signal news-specific headline patterns, and preserve concise full news sentences when they are short enough.

### Metadata
- Source: user_feedback
- Related Files: src/stages/script.py
- Tags: ai-signal, script-generation, headlines

---

## [LRN-20260428-002] correction

**Logged**: 2026-04-28T12:08:00-07:00
**Priority**: critical
**Status**: pending
**Area**: backend

### Summary
Do not claim AI Signal script quality is fixed from one inspected regenerated script; validate against the actual generated/uploaded output path and add regression tests.

### Details
User reported the script was still generating generic `AI story X` titles and disconnected title/content after prior patch. The underlying story summarization remained fragile: title generation had ad hoc fallback logic and story construction split/duplicated source notes. Fix must happen at story normalization level and be proven with tests that reject generic titles and headline/content mismatch.

### Suggested Action
Create deterministic story cards from sources/key insights, prefer source titles + source notes as paired story units, sanitize titles without generic fallbacks, and add regression tests for `AI story X` absence and first-story relevance.

### Metadata
- Source: user_feedback
- Related Files: src/stages/script.py, tests/test_script_stage.py
- Tags: ai-signal, script-quality, regression-tests

---

## [LRN-20260428-003] correction

**Logged**: 2026-04-28T12:20:00-07:00
**Priority**: critical
**Status**: pending
**Area**: backend

### Summary
AI Signal Top 5 must enforce story diversity; a technically clean script can still be bad if 4/5 stories are about one company.

### Details
User reported 4 out of 5 generated stories were about OpenAI. The issue sits in research/story selection: broad search and LLM summarization can over-cluster around OpenAI. Fix requires entity caps in research source/insight selection, not just script headline cleanup.

### Suggested Action
Cap AI Signal stories per primary entity/company, diversify search away from OpenAI-heavy queries, and test that OpenAI-heavy insights are reduced to at most two items with other companies backfilled.

### Metadata
- Source: user_feedback
- Related Files: src/stages/research.py, tests/test_script_stage.py
- Tags: ai-signal, research, story-diversity

---

## [LRN-20260428-004] correction

**Logged**: 2026-04-28T12:50:00-07:00
**Priority**: high
**Status**: pending
**Area**: ai-signal

### Summary
When an AI Signal news batch is rejected by Rafael, remove that batch from `output/covered_news.json` before regenerating so rejected/unpublished-in-practice stories do not block fresh selection.

### Details
Rafael said today's used-news entries should be cleaned because none of them were actually used. Back up the registry first, remove entries from the rejected batch/day, then run fresh research and validate before upload.

### Suggested Action
Add an explicit CLI/admin command for clearing covered-news entries by job/date to avoid manual JSON edits.

### Metadata
- Source: user_feedback
- Related Files: output/covered_news.json, src/news_registry.py
- Tags: ai-signal, registry, rejected-batch

---
## [LRN-20260509-002] correction

**Logged**: 2026-05-09T23:33:00-07:00
**Priority**: critical
**Status**: pending
**Area**: render

### Summary
Do not debug short pacing in captions/subtitles when the user says the video must follow scene planner output.

### Details
During Stoic Modernized short debugging, scene pacing complaints were partly chased in Remotion caption chunking. Rafael clarified the actual contract: scene generation is authoritative and video generation must follow scene boundaries. Future fixes must verify scene-plan-to-render mapping first before tuning subtitle/caption heuristics.

### Suggested Action
Keep renderer scene-driven, and when debugging pacing regressions inspect scene planner output and render scene transitions before touching subtitle logic.

### Metadata
- Source: user_feedback
- Related Files: frontend/src/remotion/StoicVideo.tsx, src/stages/scenes.py
- Tags: shorts, scene-planner, rendering, regression

---

## [LRN-20260515-001] correction

**Logged**: 2026-05-15T19:04:00-07:00
**Priority**: high
**Status**: pending
**Area**: render

### Summary
When a rendered video looks unchanged, verify the actual rendered frame and render props before claiming a visual fix worked.

### Details
Rafael reported that the prior rendering changes had no effect. The root issue was not an old MP4; the short was rendered in portrait mode with `platform: "youtube"`, while `StoicVideo.tsx` used `platform === "tiktok"` to choose several short-layout branches. Offset tweaks did not reliably fix the visual path because the wrong condition controlled footer/header/progress/caption behavior.

### Suggested Action
For Remotion shorts, use `mode === "portrait"` (or a derived short-layout flag) for visual layout. Keep platform as distribution metadata. Always extract frames after re-rendering and inspect them before upload or attachment.

### Metadata
- Source: user_feedback
- Related Files: frontend/src/remotion/StoicVideo.tsx
- Tags: remotion, shorts, visual-regression, verification

---

## [LRN-20260515-002] correction

**Logged**: 2026-05-15T19:09:00-07:00
**Priority**: high
**Status**: pending
**Area**: render

### Summary
Do not move established Remotion layout positions when the requested fix is to restore the existing design behavior.

### Details
Rafael asked why title, description, icon, and progress bar positions were changed. The correct scope was to restore the original short layout positions and only fix the condition that caused portrait YouTube renders to miss the short-layout branch.

### Suggested Action
When fixing a branch-selection bug, preserve all established numeric layout constants unless the user explicitly asks for visual repositioning. Confirm the diff shows condition changes only for the affected layout behavior.

### Metadata
- Source: user_feedback
- Related Files: frontend/src/remotion/StoicVideo.tsx
- Tags: remotion, shorts, scope-control, visual-regression

---
