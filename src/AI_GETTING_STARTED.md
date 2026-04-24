# AI Getting Started — Stoic Modernized

> **Baseline commit:** `d90a569a932f8f790c23469d0f6211c87c8a0878`

## Prerequisites

- Python 3.11+
- Node.js (for Remotion renderer)
- FFmpeg (for FFmpeg renderer)
- Git

## How to Set Up the AI Agent

1. **Clone the project**:
   ```
   git clone https://github.com/rafatz/stoic-modernized.git
   cd stoic-modernized
   ```

2. **Create virtual environment**:
   ```
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **Install Node.js dependencies** (for Remotion):
   ```
   cd frontend
   npm install
   cd ..
   ```

4. **Configure `.env`** (see `src/config.py` for all settings):
   ```
   cp .env.example .env  # if exists, otherwise edit manually
   ```

5. **Load agent specs**:
   - Read `AGENTS.md` for guardrails and reading order
   - Read `ai-specs/AI_NAVIGATION_INDEX.md` to find features
   - Read `ai-specs/EXTENDING.md` for decision trees

## Reading Order for AI Agents

1. `AGENTS.md` — Guardrails and reading order
2. `ai-specs/AI_NAVIGATION_INDEX.md` — Feature lookup table
3. `ai-specs/features/NNN__name.md` — Specific feature spec
4. `ai-specs/EXTENDING.md` — Decision trees and patterns
5. Source code — Search for implementation details

## Common Workflows

### Adding a New Stage

1. Read `ai-specs/features/001_pipeline_cli.md` (pipeline CLI)
2. Read `ai-specs/EXTENDING.md` → "How to Add a New Pipeline Stage"
3. Create `src/stages/<new_stage>.py` following the pattern
4. Add CLI command in `src/main.py`
5. Write feature spec in `ai-specs/features/NNN_new_stage.md`

### Changing a Provider

1. Read the relevant feature spec (e.g., `005_tts_generation.md`)
2. Check `src/config.py` for the enum and settings
3. Add provider-specific config fields
4. Add implementation method in the stage class
5. Wire into the provider selection logic
6. Update the feature spec

### Running the Pipeline (Mock Mode)

```
python -m src.main run "Stoic approaches to workplace stress" --mock
```

### Running a Single Stage

```
python -m src.main research "Stoic approaches to workplace stress" --mock
python -m src.main script <job_id> --mock
python -m src.main scene <job_id> --mock
```

### Checking Job Status

```
python -m src.main jobs
python -m src.main status <job_id>
python -m src.main retry <job_id> --stage research
```

## Tips

- **Mock mode** (`--mock`) is your safety net — always test with it first.
- **Job IDs** are UUIDs — they appear in console output after each stage.
- **Artifact paths** are stored in the SQLite database — use `status <job_id>` to find them.
- **Log files** are at `output/jobs/<job_id>/<job_id>.log` — check these for errors.
- **Configuration** is all in `src/config.py` — read it before changing any behavior.
- **When in doubt**, read the code. Code is the source of truth — specs describe the code, they don't define it.
