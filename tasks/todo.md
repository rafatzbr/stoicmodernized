# Image Prompt Specificity Repair

## Goal
Fix generic Stoic Modernized image prompts for the current `Why Status Games Drain Your Energy` video and make the scene prompt generator less generic for future workplace-status/conflict videos.

## Plan
- [x] Inspect current scene/image prompts and script context.
- [x] Patch scene prompt generation to prefer concrete workplace micro-scenes over abstract descriptors.
- [x] Update tests for the status-games prompt case.
- [x] Generate one OpenAI-Codex test image from an improved prompt and send it to Rafael.
- [x] Record lesson from the correction.

## Current diagnosis
The current prompts overuse broad phrases like `modern office professional`, `grounded contemporary office environment`, `emotionally specific action`, `small symbolic props`, and `single focal subject`. They describe a vibe, not a shootable moment. They also store the scene-plan prompt in `assets.json`, not the actual OpenAI-Codex prompt used for manual replacement, which makes quality review harder.
