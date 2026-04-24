# Stoic Modernized — YouTube Video Automation

Automate faceless YouTube video creation for Stoicism channel targeting modern workers.

## Quick Start

```bash
pip install -e ".[dev]"
python -m src.main run "Your topic here" --mock
```

## Pipeline Stages

1. **Research** — Gather sources and insights
2. **Script** — Generate narration with chapters
3. **Scene Planning** — Create visual scene plans
4. **TTS** — Generate narration audio
5. **Image Generation** — Create scene visuals
6. **Background Music** — Add ambient music
7. **Subtitles** — Generate ASR subtitles
8. **Rendering** — Produce final video (FFmpeg or Remotion)
9. **Metadata** — Generate YouTube metadata
10. **Upload** — Upload to YouTube

## AI Agent Setup

This project includes comprehensive AI specs to help agents navigate and work with the codebase effectively.

- **[AI Navigation Index](ai-specs/AI_NAVIGATION_INDEX.md)** — Feature lookup table
- **[Getting Started](AI_GETTING_STARTED.md)** — Agent setup guide
- **[EXTENDING.md](ai-specs/EXTENDING.md)** — Decision trees and patterns
- **[AGENTS.md](AGENTS.md)** — Guardrails and reading order
- **[Feature Specs](ai-specs/features/)** — Detailed specifications for each pipeline stage

**Guidance**: Read specs before making changes. Write specs before adding features.

## Configuration

All settings are in `src/config.py` and can be overridden via `.env` file.

## Channel Templates

- **Stoic Modernized** (default) — Stoicism for modern workers
- **AI Signal** — AI/tech news, urgent and precise tone
