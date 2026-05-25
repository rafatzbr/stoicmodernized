# Lessons Learned

## AI Signal Channel Cleanup (Dec 2024)

### Goal
Clean up the AI Signal channel from the stoic-modernized pipeline, keeping only Stoic Modernized functionality.

### Changes Made

#### 1. Removed AI Signal-Specific Files
- **Deleted**: `src/stages/ai_signal_pipeline.py` - Complete AI Signal pipeline implementation
- **Deleted**: Test files (`tests/test_ai_signal_*.py`)

#### 2. Cleaned Images Stage (`src/stages/images.py`)
- **Verified**: No AI Signal references exist in images.py
- **Status**: File is clean - contains only Stoic Modernized image generation code
- **Key Features Preserved**:
  - `SdServerImageGeneration` class for SD server API generation
  - `SdCliImageGeneration` class for local sd-cli generation
  - Scene mode selection (object_only, hands_only, over_shoulder, etc.)
  - Scene key identification from narration/overlay text
  - Fallback image loading from previous jobs
  - Placeholder image generation for testing
  - All prompt fragments (PROFESSIONS, ACTIONS, LOCATIONS, etc.)
  - Abstract word ban list (ABSTRACT_BAN_LIST)
  - Scene mode instructions for different visual styles

#### 2. Configuration Changes (`src/config.py`)
- Removed `AI_SIGNAL` from `Channel` enum
- Removed all `ai_signal_*` configuration variables:
  - `ai_signal_channel_name`
  - `ai_signal_channel_handle`
  - `ai_signal_channel_description`
  - `ai_signal_channel_voice`
  - `ai_signal_tts_voice`
  - `ai_signal_script_mode`
- Updated all `get_channel_*` methods to remove conditional logic for AI_SIGNAL

#### 3. Script Generation (`src/stages/script.py`)
- **Rewritten**: Complete rewrite focused only on Stoic Modernized
- Removed AI Signal-specific prompt construction
- Removed AI Signal-specific validation logic (5 story sections, title screen, etc.)
- Removed AI Signal-specific helper methods:
  - `_normalize_ai_signal_story_title`
  - `_render_ai_signal_story_body`
  - `_enforce_ai_signal_story_body`
  - `_ensure_ai_signal_story_subject`
  - `_apply_ai_signal_story_transition`
  - `_compress_ai_signal_fragment/line`
  - `_normalize_ai_signal_story_summary`
  - `_build_grounded_ai_signal_items`
  - All `_ai_signal_*` helper methods
- Simplified prompt to focus on Stoic wisdom for modern workplace challenges

#### 4. Scene Planning (`src/stages/scenes.py`)
- Removed AI Signal-specific channel checks
- Removed `_collapse_ai_signal_short_sections()` method
- Removed AI Signal-specific visual prompt generation:
  - `_ai_signal_subject()`
  - `_ai_signal_setting()`
  - `_ai_signal_action()`
  - `_ai_signal_detail()`
- Updated intro/outro branding to Stoic Modernized only
- Updated text overlay to remove AI Signal phrase mappings

#### 5. TTS Generation (`src/stages/tts.py`)
- **Rewritten**: Complete rewrite focused only on Stoic Modernized
- Removed `AISignalPipeline` import
- Removed `_run_ai_signal_timed_tts()` method
- Removed `_prepare_narration_for_tts()` method
- Removed `_apply_pronunciation_guides()` method
- Removed all AI Signal-specific helper methods:
  - `_parse_timed_blocks()`
  - `_load_script_narration()`
  - `_generate_silence_wav()`
  - `_convert_audio_to_wav()`
  - `_concat_wav_files()`
  - `_write_vtt()`
- Simplified to support only Edge TTS, ElevenLabs, and Local TTS

#### 6. Subtitle Generation (`src/stages/subtitles.py`)
- Removed `AISignalPipeline` import
- Removed AI Signal plan loading in `_retime_scene_plan_from_vtt_matches()`

#### 7. News Fetcher (`src/stages/news_fetcher.py`)
- Changed default channel from `Channel.AI_SIGNAL` to `Channel.STOIC_MODERNIZED`
- Updated query building to be generic for any topic

#### 8. OAuth Authentication (`src/auth_oauth.py`)
- Updated help text to reference only Stoic Modernized
- Removed AI Signal-specific channel directory logic

#### 9. Main CLI (`src/main.py`)
- Removed `narration-prep` command (kept in tts stage for future use)

### What Was KEPT

#### Pronunciation Dictionary (`src/stages/pronunciation_dict.py`)
- **Kept**: 150+ terms for general TTS improvement
- Covers AI models, companies, acronyms, technical terms
- General purpose, not AI Signal specific

#### Narration Prep Stage (`src/stages/narration_prep.py`)
- **Kept**: Works for both channels, keeps as general feature
- Can be enabled via `NARRATION_PREP_ENABLED` config option

#### VTT Alignment
- **Kept**: Now works correctly, general pipeline improvement

### Lessons Learned

1. **Don't Over-Engineer Channel Support**: Adding multiple channels too early creates maintenance burden
2. **Separation of Concerns**: AI Signal and Stoic Modernized have fundamentally different requirements
3. **Pronunciation Dictionary**: General-purpose TTS improvements should be channel-agnostic
4. **Narration Prep**: Can be a shared feature if designed properly
5. **Cleanup is Harder Than Initial Build**: Technical debt accumulates quickly when features diverge

### Testing Checklist
- [ ] Test Stoic Modernized script generation
- [ ] Test Stoic Modernized scene planning
- [ ] Test Stoic Modernized TTS generation (Edge, ElevenLabs, Local)
- [ ] Test Stoic Modernized image generation
- [ ] Test Stoic Modernized subtitle generation
- [ ] Test full Stoic Modernized pipeline
- [ ] Verify no AI Signal references remain in production code

### Next Steps
1. Test full pipeline with Stoic Modernized channel only
2. Monitor for any edge cases in script generation
3. Consider removing `NARRATION_PREP_ENABLED` if not needed
4. Update documentation to reflect single-channel focus

## Remotion Shorts Layout Must Follow Video Mode (May 15, 2026)

- Correction: Rafael reported that rendering changes had no visible effect.
- Root cause: the render props can be `mode: "portrait"` with `platform: "youtube"`; `frontend/src/remotion/StoicVideo.tsx` was still using `platform === "tiktok"` for key short-layout branches.
- Rule: for visual layout, derive a short-layout flag from portrait mode, not from distribution platform alone.
- Scope rule: keep the existing title, description, icon, progress, and footer position constants unless Rafael explicitly asks for repositioning. The fix is branch selection, not layout redesign.
- Verification rule: after Remotion fixes, extract representative frames from the actual MP4 and inspect them before claiming the render changed.

## Daily Cron Must Deliver Rendered Media (May 22, 2026)

- Correction: Rafael expected the completed daily Stoic Modernized video to be sent in Telegram, not only reported as `ready_for_upload`.
- Root cause: the Hermes `no_agent` cron script printed a status summary but did not emit a `MEDIA:/absolute/path.mp4` attachment line after successful render verification.
- Rule: when the daily cron finishes a render and is not uploading to YouTube, verify the exact MP4 path, nonzero size, duration, dimensions, and codecs, then include `MEDIA:<path>` in stdout so Telegram receives the video attachment.
- Failure rule: if media verification fails, treat delivery as failed and report the missing/invalid artifact instead of claiming the video is ready.

## Stoic Modernized Image Prompt Specificity (May 2026)

### Problem
Status-games video image prompts became generic because the scene planner emitted mood/vibe phrases instead of shootable moments: `modern office professional`, `grounded contemporary office environment`, `emotionally specific action`, `small symbolic props`, and `single focal subject`.

### Fix
For workplace-conflict and status-game videos, anchor each image prompt in a concrete micro-scene:
- specific location: glass meeting room, end of conference table, desk-level shot
- visible tension/action: gripping a pen, pushing phone away, sorting feedback printouts
- precise props: half-open laptop, closed notebook, water glass, phone face-down, chairs askew
- camera/light: over-the-shoulder or desk-level, shallow depth of field, natural office light
- avoid abstract nouns and generic style filler

### Verification
Added `test_status_games_visual_prompt_is_concrete_and_non_generic` in `tests/test_scenes_stage.py` and generated one OpenAI-Codex test image. The test image shows a specific post-meeting situation rather than a generic office still-life.

## Script-Level Subject Guardrail (May 2026)

### Problem
A video can pass early topic selection but still become a same-month duplicate after the generated script/title introduces overlapping trigger concepts. If validation waits until upload, the pipeline wastes scene planning, TTS, image generation, subtitles, and render work on a video that cannot be published.

### Fix
Run the duplicate/same-month subject guardrail immediately after script generation and again at the start of the `scene` command. This blocks before expensive generation stages. Keep upload-stage validation as the final safety net.

### Implementation Notes
- `YouTubeUploader.validate_script_for_generation()` reuses the same duplicate/same-month guardrail as upload.
- `src.main._validate_script_subject_before_generation()` regenerates metadata from the current script, runs validation, sets status `script_blocked`, and exits before scene/TTS/images/render.
- The helper is called immediately after `script` and again at the start of expensive downstream commands (`scene`, `tts`, `images`, `subtitles`, `render`) so manual retries cannot skip the guardrail.
- Guardrail messages should report trigger-level subject signals (for example `anxiety, meeting`), not incidental generic overlaps.
- Regression tests live in `tests/test_upload_metadata.py`.

## Metadata Titles Must Be Complete Phrases (May 2026)

### Problem
Identity-packaged metadata generation appended abstract emotion labels to otherwise complete titles, producing broken phrases such as `You Do Not Need Everyone To Like You: Stress`.

### Fix
When the Ledger topic carries missing workplace context and substantially overlaps the script title, prefer that complete contextual topic over adding an abstract `: Stress` / `: Anxiety` suffix. Keep suffix rewrites only for title formulas where the emotion label becomes grammatical, such as `Why Anxiety Keeps Running Your Work Life`.

### Verification
Added `test_resolve_metadata_title_prefers_contextual_ledger_topic_over_fragment_suffix` in `tests/test_upload_metadata.py`. Run `python -m pytest tests/test_upload_metadata.py -q` after metadata-title changes.


## Kokoro Scene-Plan Subtitle Fallback Must Scale to Audio Duration (May 2026)

### Problem
Rafael caught a placeholder Kokoro smoke-test video where narration and subtitles were badly out of sync. The scene planner estimated 54 seconds, but Kokoro rendered 33.088 seconds of continuous narration. The subtitle fallback kept the 54-second scene timings because the scale ratio was outside the old 0.85–1.25 guard, then `_polish_segments()` clamped cues to the audio duration. That truncated the late narration captions and produced a broken VTT.

### Fix
For audio-only/provider-neutral fallback subtitles, scale scene-plan cue boundaries to the measured narration duration whenever `audio_duration` is available. Never clamp a longer estimated scene plan to audio duration without scaling first.

### Verification
Added `test_scene_plan_fallback_scales_all_scene_text_to_actual_audio_duration` in `tests/test_subtitle_heuristic_vtt_sidecar.py`. Run the subtitle/VTT subset after touching this path.

## Kokoro Subtitle Readability Windows (May 2026)

### Problem
Rafael reported a Kokoro Shorts render that felt too slow while phrase subtitles disappeared too fast. The render used `kokoro_speed=0.66`, and forced-aligned cue retiming displayed exact first/last spoken-word spans, making short captions such as “It is ownership.” visible for well under a readable hold time.

### Fix
Use a calmer-but-moving Kokoro default (`kokoro_speed=0.76`) and keep alignment as the sync source, not the display-duration policy. Group aligned words into short phrase cues and apply readability windows that extend short phrases through available pauses without overlapping the next cue.

### Verification
Before rendering, inspect subtitle metrics for minimum cue duration and high-CPS short cues. Regression coverage lives in `tests/test_subtitle_timing.py` and `tests/test_subtitle_forced_alignment.py`.
