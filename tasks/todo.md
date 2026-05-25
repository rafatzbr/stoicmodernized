# TTS/VTT Staged Implementation

## Goal
Add a provider-neutral TTS timing/subtitle layer for Stoic Modernized video workflows, starting with readable phrase-level WebVTT helpers that can normalize EdgeTTS/native timing now and support Kokoro + forced alignment later.

## Current architecture notes
- `src/stages/tts.py` currently hard-wires Edge TTS and writes `output/jobs/<job-id>/audio/narration.mp3` plus `audio/narration.vtt` via `edge-tts --write-subtitles`.
- `src/stages/subtitles.py` currently reads Edge's `audio/narration.vtt`, otherwise falls back through ASR and scene/script heuristics, then writes `subtitles/subtitles.srt` and `subtitles/subtitles.json`.
- Existing subtitle helpers already split text into readable phrases and produce SRT, but there is no provider-neutral timing model/WebVTT writer yet.
- Relevant specs: `005_tts_generation.md`, `008_subtitle_generation.md`, and `EXTENDING.md`.

## Staged plan
- [x] Inspect current TTS/subtitle architecture and AI specs.
- [x] Stage 1: Add provider-neutral timing models/helper functions and WebVTT writer with tests.
  - `TimedWord`: text/start/end/source/confidence.
  - `TimedCue`: text/start/end/source/words.
  - phrase grouping from native word timing into readable cues.
  - deterministic WebVTT formatting with monotonic validation and final newline.
- [x] Stage 2: Refactor Edge TTS subtitle ingestion to normalize through the timing helper while preserving existing output behavior.
- [x] Stage 3: Add heuristic VTT fallback from text + audio duration for audio-only providers.
- [x] Stage 4: Add video-workflow subtitle config flags (`format=vtt`, `timing=auto`, readable phrase style, fallback policy) without affecting Hermes voice replies.
- [x] Stage 5: Add Kokoro provider as the first local natural narration provider, using heuristic/alignment-compatible VTT sidecars.
- [x] Stage 6: Add optional forced-alignment path (`stable-ts`/Whisper-family) once base provider-neutral VTT is stable.
- [x] Update AI specs and README as behavior changes land.
- [x] Run targeted tests after each stage and broader tests before any commit.

## Stage 1 verification
- [x] RED: wrote tests that import the desired `src.subtitle_timing` API and confirmed they failed before implementation (`ModuleNotFoundError: No module named 'src.subtitle_timing'`).
- [x] GREEN: implemented only the helper API required by those tests.
- [x] Verified with `.venv/bin/python -m pytest tests/test_subtitle_timing.py -q`.
- [x] Ran affected existing subtitle/TTS tests: `.venv/bin/python -m pytest tests/test_subtitle_timing.py tests/test_scene_retiming.py tests/test_tts_stage.py -q`.

## Review notes
- Added `src/subtitle_timing.py` with provider-neutral `TimedWord`, `TimedCue`, readable cue grouping, heuristic cue generation, WebVTT parsing, and deterministic WebVTT formatting.
- Added `tests/test_subtitle_timing.py` for native word grouping, VTT formatting/parsing, and heuristic timing.
- Added `tests/test_subtitle_edge_vtt_ingestion.py` to prove `SubtitleStage` loads EdgeTTS VTT sidecars through the normalized timing helper.
- Updated `008_subtitle_generation.md` and `013_cross_cutting.md` to document the timing helper layer and Edge/WebVTT normalization.
- Stage 2 verification passed: `.venv/bin/python -m pytest tests/test_subtitle_timing.py tests/test_subtitle_edge_vtt_ingestion.py tests/test_scene_retiming.py tests/test_tts_stage.py -q` (`7 passed`) plus `py_compile` for `src/subtitle_timing.py` and `src/stages/subtitles.py`.
- Stage 3 writes `subtitles/subtitles.vtt` from the final polished subtitle segments, so audio-only providers using ASR/scene/script heuristics receive the same provider-neutral WebVTT sidecar as native/Edge timing paths.
- Stage 3 verification passed: RED failed because `subtitles.vtt` did not exist; GREEN passed with `.venv/bin/python -m pytest tests/test_subtitle_heuristic_vtt_sidecar.py -q`; affected suite passed with `.venv/bin/python -m pytest tests/test_subtitle_timing.py tests/test_subtitle_edge_vtt_ingestion.py tests/test_subtitle_heuristic_vtt_sidecar.py tests/test_scene_retiming.py tests/test_tts_stage.py -q` (`8 passed`).
- Stage 4 added video-scoped subtitle config flags: `tts_subtitles_enabled`, `tts_subtitles_format`, `tts_subtitles_timing`, `tts_subtitles_phrase_style`, and `tts_subtitles_fallback`. The subtitle stage now honors the enabled/format flags before writing `subtitles.vtt`; SRT/JSON output remains unchanged.
- Stage 4 verification passed: RED failed because the config fields did not exist; GREEN passed with `.venv/bin/python -m pytest tests/test_subtitle_config.py -q`; affected suite passed with `.venv/bin/python -m pytest tests/test_subtitle_config.py tests/test_subtitle_timing.py tests/test_subtitle_edge_vtt_ingestion.py tests/test_subtitle_heuristic_vtt_sidecar.py tests/test_scene_retiming.py tests/test_tts_stage.py -q` (`10 passed`) plus `py_compile` for `src/config.py`, `src/subtitle_timing.py`, and `src/stages/subtitles.py`.
- Stage 5 added `TTSProvider.KOKORO`, Kokoro settings, provider alias normalization, a `KokoroTTSAudio` command provider, and CLI help for `edge`/`kokoro`. Kokoro deliberately passes no native `subtitles_path`; final VTT timing remains owned by the subtitle stage.
- Stage 5 verification passed: RED failed because `KokoroTTSAudio`/config did not exist; GREEN passed with `.venv/bin/python -m pytest tests/test_tts_kokoro_provider.py -q`; affected suite passed with `.venv/bin/python -m pytest tests/test_tts_kokoro_provider.py tests/test_tts_stage.py tests/test_config.py tests/test_subtitle_config.py tests/test_subtitle_heuristic_vtt_sidecar.py -q` (`25 passed`) plus `py_compile` for `src/config.py`, `src/stages/tts.py`, `src/stages/subtitles.py`, and `src/main.py`.
- Stage 6 target: optional forced-alignment path (`stable-ts`/Whisper-family) after the Kokoro command path is verified on a real installed voice.
- Stage 6 added an opt-in forced-alignment path for `stable-ts`/`stable_whisper`: `tts_subtitles_timing=align` tries alignment before ASR, while `auto` only attempts alignment when `tts_subtitles_alignment_enabled=true`. Aligned words are normalized as `TimedWord`, grouped into readable cues, and preserved in `SubtitleSegment.words`; if the aligner is unavailable or returns no words, the stage falls back to the existing ASR/heuristic paths.
- Stage 6 verification passed: RED failed because alignment config/helper methods did not exist; GREEN passed with `.venv/bin/python -m pytest tests/test_subtitle_forced_alignment.py -q`; affected suite passed with `.venv/bin/python -m pytest tests/test_subtitle_forced_alignment.py tests/test_subtitle_config.py tests/test_subtitle_timing.py tests/test_subtitle_edge_vtt_ingestion.py tests/test_subtitle_heuristic_vtt_sidecar.py tests/test_tts_kokoro_provider.py tests/test_tts_stage.py tests/test_config.py -q` (`32 passed`) plus `py_compile` for `src/config.py`, `src/subtitle_timing.py`, `src/stages/subtitles.py`, `src/stages/tts.py`, and `src/main.py`.
- Hardening pass removed accidental generated frontend media/public artifacts and reverted unrelated social-explorer/upload metadata changes from this TTS/VTT diff.
- Hardening fixes added after review: Kokoro now falls back to the configured CLI when direct `kokoro_onnx` rendering fails, disabled VTT config removes stale `subtitles/subtitles.vtt`, WebVTT parsing strips cue markup/inline timestamps, and the old mock-mode error no longer says Edge is the only real provider.
- Full-suite verification passed: `.venv/bin/python -m pytest -q` (`177 passed, 15 warnings`) after updating the stale short-mode visual prompt assertion to match the current concrete 9:16 workplace prompt style.

## Notes / guardrails
- Subtitles stay scoped to video workflows.
- Final captions should be readable phrase cues, not one-word karaoke.
- Forced-aligned Kokoro captions need readability display windows; do not use exact first/last word spans for cue display duration.
- Prefer open-source/commercial-safe local voices, but keep quality exceptions explicit.
- Do not touch `.env` or credentials.
- Do not push without Rafael asking.
