#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
VENV_DIR="$REPO_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Error: virtual environment not found at $VENV_DIR" >&2
  exit 1
fi

if [ ! -f "$VENV_DIR/bin/activate" ]; then
  echo "Error: activate script not found at $VENV_DIR/bin/activate" >&2
  exit 1
fi

# shellcheck disable=SC1091
. "$VENV_DIR/bin/activate"

cd "$REPO_DIR"
exec python -m src.main ui-dev "$@"
