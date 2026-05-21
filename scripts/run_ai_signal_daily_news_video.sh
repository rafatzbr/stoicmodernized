#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/rafatz/projects/stoic-modernized"
cd "$REPO_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Generate a short Top 5 AI news video for The AI Signal and upload it.
# The pipeline deduplicates previously covered AI Signal sources via output/covered_news.json.
python -m src.main run \
  "Top 5 AI News" \
  --channel ai-signal \
  --video-mode short \
  --renderer remotion \
  --platform tiktok
