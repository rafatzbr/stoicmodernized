#!/usr/bin/env python3
"""Add a local audio file to the curated Stoic Modernized music library.

Example:
  python3 music/add_track.py /path/to/file.mp3 \
    --title "Calm Bed 01" \
    --artist "YouTube Audio Library" \
    --license "YouTube Audio Library" \
    --source-url "https://studio.youtube.com/" \
    --moods calm ambient minimal
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_DIR = PROJECT_ROOT / "music"
TRACKLIST_PATH = LIBRARY_DIR / "tracklist.json"
TRACKS_DIR = LIBRARY_DIR / "tracks"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "track"


def audio_duration_seconds(path: Path) -> float | None:
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(probe.stdout.strip())
    except Exception:
        return None


def load_tracklist() -> dict[str, Any]:
    if TRACKLIST_PATH.exists():
        return json.loads(TRACKLIST_PATH.read_text())
    return {"version": 1, "tracks": []}


def save_tracklist(payload: dict[str, Any]) -> None:
    TRACKLIST_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a track to the curated music library")
    parser.add_argument("source_file")
    parser.add_argument("--title", required=True)
    parser.add_argument("--artist", required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--moods", nargs="*", default=["calm", "ambient", "minimal"])
    parser.add_argument("--category", default="ambient")
    parser.add_argument("--attribution-required", action="store_true")
    parser.add_argument("--attribution-text")
    parser.add_argument("--approved-for-youtube", action="store_true", default=True)
    args = parser.parse_args()

    src = Path(args.source_file).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"Source file not found: {src}")

    category_dir = TRACKS_DIR / slugify(args.category)
    category_dir.mkdir(parents=True, exist_ok=True)
    stem = slugify(f"{args.artist}-{args.title}")
    dest = category_dir / f"{stem}{src.suffix.lower()}"
    shutil.copy2(src, dest)

    rel_path = dest.relative_to(LIBRARY_DIR)
    payload = load_tracklist()
    tracks = payload.setdefault("tracks", [])
    track_id = stem
    if any(track.get("id") == track_id for track in tracks):
        raise SystemExit(f"Track id already exists: {track_id}")

    tracks.append(
        {
            "id": track_id,
            "title": args.title,
            "artist": args.artist,
            "path": str(rel_path),
            "license": args.license,
            "source_url": args.source_url,
            "approved_for_youtube": bool(args.approved_for_youtube),
            "instrumental": True,
            "low_background": True,
            "attribution_required": bool(args.attribution_required),
            "attribution_text": args.attribution_text,
            "moods": args.moods,
            "duration": audio_duration_seconds(dest),
          }
    )
    save_tracklist(payload)
    print(dest)


if __name__ == "__main__":
    main()
