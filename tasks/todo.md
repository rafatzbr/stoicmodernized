# Script variety guardrail

- [x] Inspect recent Stoic script artifacts for repeated topic/opening patterns.
- [x] Add regression coverage for repeated `Your boss ...` opener and near-duplicate recent scripts.
- [x] Patch script generation prompts and validation to avoid repeated openings and too-similar recent scripts.
- [x] Update script-generation spec and lessons.
- [x] Run targeted tests and verify the current problematic script is now rejected.

## Review

Rafael flagged that the latest script was too similar to a recent video and that the last two starts included `Your boss ...`. Recent artifact inspection confirmed repeated priority-shift/`Your boss` openings. Added recent-script negative context to script drafting and quality gates that reject repeated opener patterns and term-heavy near-duplicates before scene planning/rendering. Verified with `tests/test_script_stage.py` and direct validation of job `ebe20fed-5716-4d70-8bad-4dd89e5ed666`, which now rejects with `repeats recent opener pattern: your boss`.

# Media explorer relevant tag limit

- [x] Find media explorer description/tag generation code and tests.
- [x] Add regression coverage: media explorer captions emit no more than 5 hashtags and skip unrelated metadata tags.
- [x] Patch caption/tag selection to prefer context-relevant tags.
- [x] Run targeted tests and syntax checks.

## Review

Media explorer/helper-page descriptions now build their hashtag tail from title/description context. The selection keeps Stoicism/channel branding, then only includes metadata tags with distinctive token overlap against the actual title/description, capped at five tags total. Verified with `tests/test_social_distribution.py` and `py_compile` for `src/stages/social_distribution.py` plus `scripts/generate_social_public_explorer.py`.
