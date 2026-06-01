# Active plan — tighten validation and regenerate video

## Goal
Make early subject validation match final upload cooldown behavior, generate a replacement video, and schedule it on YouTube for June 2, 2026 at 8 AM Pacific.

## Completed
- [x] Root-caused early/upload validation disagreement: metadata maintenance rewrites refreshed old file mtimes, so upload treated older jobs as recent.
- [x] Added regression coverage for edited old metadata and metadata missing dates.
- [x] Patched cooldown date logic to prefer stable metadata/ledger/script dates before file mtime.
- [x] Verified targeted upload metadata tests, daily orchestrator tests, py_compile, and daily setup check.
- [x] Generated replacement video `d2ca9c28-cc30-4614-b6fb-c0ceaeeb75cf` after guardrail-aware topic retry.
- [x] Repaired final YouTube metadata description before upload; verified exactly five hashtags.
- [x] Verified MP4, music guardrail, duplicate/topic guardrail, and scheduled YouTube upload.

## Upload result
- Job ID: `d2ca9c28-cc30-4614-b6fb-c0ceaeeb75cf`
- YouTube video ID: `wW9ma_TT0Lg`
- URL: https://www.youtube.com/watch?v=wW9ma_TT0Lg
- Schedule: `2026-06-02T15:00:00Z` (June 2, 8:00 AM Pacific)
- Verified API state: `privacyStatus=private`, `uploadStatus=processed`, `processingStatus=succeeded`, `duration=PT1M1S`, `definition=hd`

## Notes
- Do not bypass upload guardrails.
- The standard CLI upload regenerates metadata; for this run the direct uploader path was used after cleaning bad generated description copy.
