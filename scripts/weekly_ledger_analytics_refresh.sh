#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/home/rafatz/projects/stoic-modernized"
LOG_DIR="$PROJECT_ROOT/output/automation"
mkdir -p "$LOG_DIR"

cd "$PROJECT_ROOT"
source .venv/bin/activate
python -m src.refresh_youtube_analytics --lookback-days 28 >> "$LOG_DIR/weekly_ledger_analytics_refresh.log" 2>&1
