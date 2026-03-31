# Stoic Modernized

Automate faceless YouTube video creation for the **Stoic Modernized** channel, targeting modern workers, knowledge workers, and professionals interested in applying Stoic philosophy to workplace challenges.

## Features

- **CLI-based pipeline** for complete video automation
- **Mock mode** for testing without API keys
- **SQLite job tracking** with retry support
- **Per-stage JSON outputs** for transparency and debugging
- **Modular provider abstractions** for TTS, image generation, and YouTube upload
- **Real local asset generation** for WAV narration, JPEG scene cards, SRT subtitles, and MP4 rendering
- **1080p output** with ffmpeg-based rendering
- **Structured logging** per job

## Quick Start

### Prerequisites

- Python 3.11+
- ffmpeg + ffprobe
- ImageMagick (`convert`) for local scene-card image generation
- Stable Diffusion CLI (optional, only if you want model-based image generation instead of local generated cards)

### Installation

```bash
# Install dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env

# Edit .env and add your API keys (optional - mock mode works without)
```

### Running the Pipeline

The pipeline has multiple stages that can be run individually or as a complete flow.

#### Generate Ideas

```bash
python -m src.main idea --count 5 --mock
```

#### Research a Topic

```bash
python -m src.main research --topic "handling workplace stress" --mock
# or attach to existing job
python -m src.main research --topic "handling workplace stress" --job-id <job-id> --mock
```

#### Generate Script

```bash
python -m src.main script --job-id <job-id> --mock
```

#### Create Scene Plan

```bash
python -m src.main scene --job-id <job-id> --mock
```

#### Generate TTS Audio

```bash
python -m src.main tts --job-id <job-id> --mock
```

#### Generate Images

```bash
python -m src.main images --job-id <job-id> --mock
```

#### Generate Subtitles

```bash
python -m src.main subtitles --job-id <job-id> --mock
```

#### Render Video

```bash
python -m src.main render --job-id <job-id> --mock
```

#### Generate YouTube Metadata

```bash
python -m src.main metadata --job-id <job-id> --mock
```

#### Upload to YouTube

```bash
python -m src.main upload --job-id <job-id> --mock
```

#### Run Complete Pipeline

```bash
python -m src.main run --topic "handling workplace stress" --mock
```

#### View Jobs

```bash
python -m src.main jobs
python -m src.main jobs --status completed
python -m src.main status <job-id>
```

#### Retry Failed Stage

```bash
python -m src.main retry <job-id> --stage research --mock
python -m src.main retry <job-id> --mock  # retry from beginning
```

## Configuration

### Environment Variables

See `.env.example` for all available options.

| Variable | Description | Default |
|----------|-------------|---------|
| `MOCK_MODE` | Enable mock mode for all stages | `false` |
| `TTS_API_KEY` | ElevenLabs API key (optional) | - |
| `YOUTUBE_API_KEY` | YouTube Data API key (optional) | - |
| `YOUTUBE_PRIVACY_STATUS` | Video privacy: public, unlisted, private | `unlisted` |

### Video Settings

- **Output Resolution**: 1920x1080 (1080p)
- **FPS**: 30
- **Background Music Volume**: 15%

### TTS Settings

- **Default Provider**: local (mock)
- **Supported Providers**: local, elevenlabs
- **Default Voice**: adam

### Image Generation Settings

- **Provider**: sd-cli (stable-diffusion.cpp)
- **Output Resolution**: 1080x1920 (vertical for YouTube Shorts/Reels)
- **Sampling Method**: euler

## Project Structure

```
src/
├── main.py           # CLI entry point with all commands
├── config.py         # Pydantic settings with env loading
├── models.py         # Pydantic data models
├── database.py       # SQLite job tracking with SQLAlchemy
├── utils.py          # Helper functions (JSON, paths, etc.)
├── logging_config.py # Job-specific and pipeline logging
├── stages/
│   ├── research.py   # Research and source gathering
│   ├── script.py     # Script generation
│   ├── scenes.py     # Scene planning from script
│   ├── tts.py        # Text-to-speech audio generation
│   ├── images.py     # Image generation for scenes
│   ├── subtitles.py  # SRT subtitle generation
│   ├── render.py     # ffmpeg video rendering
│   └── upload.py     # YouTube upload (stub)
```

## Pipeline Stages

| Stage | Input | Output |
|-------|-------|--------|
| research | topic | research.json (sources, insights) |
| script | research.json | script.json (narration, chapters) |
| scenes | script.json | scenes.json (scene breakdown, visual prompts) |
| tts | scenes.json | narration.wav |
| images | scenes.json | scene_XXX.jpg (one per scene) |
| subtitles | script.json | subtitles.srt, subtitles.json |
| render | all assets | final.mp4, thumbnail.jpg |
| metadata | script.json, scenes.json | metadata.json (title, description, tags) |
| upload | video, metadata | YouTube video URL |

## Mock Mode

Mock mode is enabled by default when:
- `MOCK_MODE=true` in .env
- `--mock` flag is passed to any command

In mock mode:
- Research generates sample Stoic sources
- Scripts are templated with Stoic wisdom
- Images are still generated as local scene cards
- Audio is still generated as a local WAV narration track
- Video rendering still creates a real MP4 from generated assets
- Upload returns a mock YouTube URL

This means the local pipeline remains testable end-to-end even without external APIs or model backends.

## Brand Voice

The Stoic Modernized channel follows these guidelines:

- **Calm, practical, concise, modern**
- **Not preachy, not academic**
- **Avoid cheesy motivational language**
- **Always translate Stoic ideas into concrete workplace situations**

## Provider Implementations

### TTS Providers

- **local**: Generates a real WAV narration asset locally without requiring external APIs
- **elevenlabs**: Real ElevenLabs API integration when credentials are configured; otherwise the pipeline safely falls back to local generation

### Image Generation

- **sd_cli**: Integration with stable-diffusion.cpp CLI when local models are available
- **local fallback**: Generates branded scene-card JPEGs with ImageMagick when sd-cli or models are unavailable
- **dall_e**: Placeholder for DALL-E 3 API (stub)

### YouTube Upload

- **google-api-python-client**: Real upload requires API key configuration
- Currently uses mock upload in mock mode

## Troubleshooting

### Common Issues

1. **"Job not found"**: Make sure you ran the research stage first, or use the correct job ID from `python -m src.main jobs`

2. **Missing assets**: Each stage depends on previous stage outputs. Run stages in order or use `python -m src.main run --topic "..." --mock`

3. **Mock mode not working**: Check that `MOCK_MODE` is not set to `true` in your .env, or add `--mock` flag to commands

4. **ffmpeg errors**: Install ffmpeg: `apt-get install ffmpeg` or `brew install ffmpeg`

## License

MIT
