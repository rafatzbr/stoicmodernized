# Stoic Modernized

Automate faceless YouTube video creation for the **Stoic Modernized** channel, targeting modern workers, knowledge workers, and professionals interested in applying Stoic philosophy to workplace challenges.

## Features

- **CLI-based pipeline** for complete video automation
- **Mock mode** for testing without API keys
- **SQLite job tracking** with retry support
- **Per-stage JSON outputs** for transparency and debugging
- **Modular provider abstractions** for TTS, image generation, and YouTube upload
- **Real local asset generation** for narration, JPEG scene cards, SRT subtitles, and MP4 rendering
- **Shorts + long-video modes** with vertical and landscape outputs
- **Firefox-friendlier MP4 output** with browser-safe H.264/AAC settings
- **Structured logging** per job
- **OAuth2 YouTube upload** - Upload videos directly to your channel

## Image Prompt Generation

The pipeline now uses a **base prompt template with llama.cpp refinement** to generate varied, valid image prompts.

### How It Works

1. **Base Template** - Defines the visual identity for Stoic Modernized channel
2. **Random Expansion** - Combines professions, actions, locations, objects randomly
3. **llama.cpp Refinement** - Qwen3.5 model expands the base into a detailed prompt
4. **Seed Management** - Each scene gets a unique seed to ensure variety

### Manual Testing

```bash
cd /home/rafatz/projects/stoic-modernized
python -m src.prompt_generator "staying calm when work feels urgent"
```

### Automatic Generation

The image generation stage (`src/stages/images.py`) automatically uses this system:

- Each scene gets a random seed from `src/prompt_seed.json`
- Predefined elements are combined randomly
- llama.cpp refines into a detailed prompt
- Output is sanitized and validated before use

### Predefined Elements

You can customize these in `src/stages/images.py`:

- **PROFESSIONS** - Types of people/workers
- **ACTIONS** - What they're doing
- **LOCATIONS** - Where the scene takes place
- **CONCRETE_OBJECTS** - Items visible in the scene
- **BACKGROUNDS** - Background details
- **FOREGROUNDS** - Foreground details

Each run randomly combines these, so prompts vary while maintaining the channel identity.

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

# For VoxCPM TTS provider (optional):
pip install -e ".[tts-voxcpm]"

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
python -m src.main research --topic "your topic here" --mock
```

#### Create Script

```bash
python -m src.main script --job-id <job_id> --mock
```

#### Generate Audio

```bash
python -m src.main tts --job-id <job_id> --mock
```

**VoxCPM TTS Provider**:

VoxCPM is a state-of-the-art tokenizer-free multilingual TTS system. This implementation uses **VoxCPM.cpp**, a C++ CLI tool supporting CPU, CUDA, and Vulkan backends.

```bash
# Build VoxCPM.cpp
git clone https://github.com/bluryar/VoxCPM.cpp
cd VoxCPM.cpp
cmake -B build
cmake --build build -j$(nproc)

# Download model
mkdir -p ~/models/voxcpm
wget https://huggingface.co/bluryar/VoxCPM-GGUF/resolve/main/voxcpm1.5-q8_0-audiovae-f16.gguf \
  -O ~/models/voxcpm/voxcpm1.5-q8_0-audiovae-f16.gguf

# Configure in .env
TTS_PROVIDER=voxcpm
TTS_VOICE="calm, deep male voice"  # Optional: voice design description
VOXCPM_MODEL_PATH=/home/rafatz/models/voxcpm/voxcpm1.5-q8_0-audiovae-f16.gguf
VOXCPM_BACKEND=auto  # cpu, cuda, or vulkan

# Run pipeline with VoxCPM
python -m src.main tts --job-id <job_id>
```

Features:
- **30-language multilingual** support
- **Voice Design**: Create voices from text descriptions
- **Voice Cloning**: Clone from reference audio
- **48kHz studio-quality** output
- **Multiple backends**: CPU, CUDA (NVIDIA), or Vulkan (cross-platform GPU)
- **Open source**: Apache-2.0 licensed

See **[docs/VOXCPM_TTS.md](docs/VOXCPM_TTS.md)** for detailed setup instructions.
- **48kHz studio-quality** output
- **Real-time streaming** support (RTF ~0.3 on RTX 4090)

See [VoxCPM documentation](https://github.com/OpenBMB/VoxCPM) for more details.

#### Generate Images

```bash
python -m src.main images --job-id <job_id> --mock
```

#### Generate Subtitles

```bash
python -m src.main subtitles --job-id <job_id> --mock
```

#### Render Video

```bash
python -m src.main render --job-id <job_id> --mock
```

#### Upload to YouTube

```bash
python -m src.main upload --job-id <job_id>
```

### Running the Full Pipeline

```bash
python -m src.main run --video-mode short --mock
```

## Configuration

Edit `.env` to configure:

### TTS Configuration

- `TTS_PROVIDER` - TTS provider (`local`, `edge`, `elevenlabs`, or `voxcpm`)
- `TTS_VOICE` - Voice to use (for ElevenLabs or voice design for VoxCPM)
- `TTS_SPEED` - Speech speed multiplier (0.25 to 4.0, default: 1.0)
- `VOXCPM_MODEL_PATH` - VoxCPM model path (optional, for VoxCPM provider)

### Image Generation Configuration

The pipeline supports **two image generation methods**:

1. **SD Server (Recommended)** - Connects to a local SD server (Automatic1111 or ComfyUI)
2. **SD CLI** - Uses stable-diffusion.cpp CLI directly

If SD server is available, it will be used automatically. Otherwise, SD CLI is used.

**SD Server Settings:**
- `SD_SERVER_URL` - SD server URL (default: `http://localhost:1234`)
- `SD_SERVER_API_PATH` - API endpoint (default: `/sdapi/v1/txt2img`)
- `SD_SERVER_TIMEOUT_SECONDS` - Request timeout (default: 300)

**SD CLI Settings:**
- `SD_CLI_PATH` - Path to sd-cli executable
- `SD_MODEL_PATH` - Stable Diffusion model path
- `SD_CLIP_L_PATH`, `SD_CLIP_G_PATH`, `SD_T5XXL_PATH` - CLIP and T5 model paths
- `SD_IMAGE_WIDTH`, `SD_IMAGE_HEIGHT` - Output dimensions
- `SD_CFG_SCALE`, `SD_STEPS`, `SD_SAMPLING_METHOD` - Generation parameters
- `SD_NEGATIVE_PROMPT` - Negative prompt

### YouTube Configuration

- `YOUTUBE_API_KEY` - YouTube API key (for upload)
- `YOUTUBE_CREDENTIALS_PATH` - Path to OAuth2 credentials JSON file (optional)
- `YOUTUBE_PRIVACY_STATUS` - Upload privacy (`public`, `unlisted`, or `private`)
- `YOUTUBE_SCHEDULE_DATETIME` - Schedule upload in ISO 8601 format (optional)

### Other Settings

- `MOCK_MODE` - Enable mock mode (`true` or `false`)
- `FORCE_PLACEHOLDER_IMAGES` - Use local generated cards instead of SD (`true` or `false`)

## YouTube Upload Setup

See **[YOUTUBE_UPLOAD.md](YOUTUBE_UPLOAD.md)** for detailed setup instructions.

Quick setup:
```bash
# Install OAuth2 dependencies
pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2

# Download OAuth2 credentials from Google Cloud Console
# Place in ~/.stoic-modernized/client_secret.json or set YOUTUBE_CREDENTIALS_PATH

# Authenticate
python -m src.auth_oauth

# Upload video
python -m src.main upload <job_id>
```

## Architecture

```
src/
├── main.py          # CLI entry point
├── config.py        # Settings and configuration
├── database.py      # SQLite database operations
├── models.py        # Data models
├── logging_config.py # Logging setup
├── utils.py         # Utility functions
├── stages/
│   ├── research.py      # Topic research
│   ├── script.py        # Script generation
│   ├── tts.py           # Text-to-speech (local, edge, elevenlabs, voxcpm)
│   ├── images.py        # Image generation (SD CLI, SD Server, or local fallbacks)
│   ├── subtitles.py     # Subtitle generation
│   ├── render.py        # Video rendering
│   └── upload.py        # YouTube upload
└── prompt_generator.py  # Prompt generation (NEW)
```

## License

MIT License
