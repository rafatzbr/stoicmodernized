# VoxCPM TTS Provider

VoxCPM is a state-of-the-art tokenizer-free Text-to-Speech system. This implementation uses **VoxCPM.cpp**, a C++ CLI tool that supports CPU, CUDA, and Vulkan backends for flexible deployment.

## Features

- **30-Language Multilingual**: Supports Arabic, Burmese, Chinese, Danish, Dutch, English, Finnish, French, German, Greek, Hebrew, Hindi, Indonesian, Italian, Japanese, Khmer, Korean, Lao, Malay, Norwegian, Polish, Portuguese, Russian, Spanish, Swahili, Swedish, Tagalog, Thai, Turkish, Vietnamese (plus Chinese dialects)
- **Voice Design**: Create voices from natural-language descriptions (gender, age, tone, emotion, pace)
- **Voice Cloning**: Clone voices from reference audio clips
- **48kHz Studio Quality**: Native high-quality audio output
- **Multiple Backends**: CPU, CUDA (NVIDIA GPU), or Vulkan (cross-platform GPU)
- **Open Source**: Apache-2.0 licensed, free for commercial use

## Installation

### Requirements

- CMake ≥ 3.20
- C++ compiler (GCC, Clang, or MSVC)
- Optional: NVIDIA CUDA toolkit (for GPU acceleration)
- Optional: Vulkan SDK (for Vulkan backend)

### Install and Build VoxCPM.cpp

```bash
# Clone the repository
git clone https://github.com/bluryar/VoxCPM.cpp
cd VoxCPM.cpp

# Build for CPU
cmake -B build
cmake --build build -j$(nproc)

# OR build with CUDA support (optional)
cmake -B build-cuda -DVOXCPM_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89
cmake --build build-cuda -j$(nproc)

# OR build with Vulkan support (optional, for non-NVIDIA GPUs)
cmake -B build-vulkan -DVOXCPM_VULKAN=ON
cmake --build build-vulkan -j$(nproc)
```

### Download Model

Download a quantized model from Hugging Face: https://huggingface.co/bluryar/VoxCPM-GGUF

```bash
# Recommended models:
# - voxcpm1.5-q8_0-audiovae-f16.gguf (942MB, balanced quality/speed)
# - voxcpm-0.5b-q4_K.gguf (477MB, fastest)

mkdir -p ~/models/voxcpm
cd ~/models/voxcpm

# Download voxcpm1.5 (balanced)
wget https://huggingface.co/bluryar/VoxCPM-GGUF/resolve/main/voxcpm1.5-q8_0-audiovae-f16.gguf

# OR download voxcpm-0.5b (fastest, smaller)
wget https://huggingface.co/bluryar/VoxCPM-GGUF/resolve/main/voxcpm-0.5b-q4_K.gguf
```

## Configuration

Add to `.env`:

```ini
TTS_PROVIDER=voxcpm
TTS_VOICE="calm, deep male voice"  # Optional: voice design description
VOXCPM_MODEL_PATH=openbmb/VoxCPM2  # Optional: defaults to VoxCPM2
TTS_SPEED=1.0  # Optional: 0.5 to 2.0
```

## Usage

### In the Pipeline

```bash
# Set TTS provider in .env
TTS_PROVIDER=voxcpm

# Run the pipeline
python -m src.main run "your topic here"
```

### Voice Design

Specify voice characteristics in the `TTS_VOICE` environment variable:

```ini
TTS_VOICE="calm, professional male voice, slightly slow pace"
```

The voice description is prepended to the text during generation:
```
(calm, professional male voice, slightly slow pace)Welcome to Stoic Modernized...
```

### Voice Cloning

To use voice cloning, you need a reference audio file. This requires modifying the `VoxCPMTTS` class to accept a reference audio path. See the VoxCPM documentation for advanced usage.

## Model Options

VoxCPM offers three model versions:

| Model | Parameters | Languages | VRAM | RTF (RTX 4090) |
|-------|-----------|-----------|------|----------------|
| VoxCPM2 | 2B | 30 | ~8 GB | ~0.30 |
| VoxCPM1.5 | 0.6B | 2 (zh, en) | ~6 GB | ~0.15 |
| VoxCPM-0.5B | 0.5B | 2 (zh, en) | ~5 GB | ~0.17 |

### Model Selection

```ini
# Latest and recommended (VoxCPM2)
VOXCPM_MODEL_PATH=openbmb/VoxCPM2

# Faster, lower VRAM (VoxCPM1.5 - Chinese & English only)
VOXCPM_MODEL_PATH=openbmb/VoxCPM1.5

# Lowest VRAM (VoxCPM-0.5B - Chinese & English only)
VOXCPM_MODEL_PATH=openbmb/VoxCPM-0.5B
```

## Performance

### Hardware Requirements

- **Minimum**: NVIDIA GPU with 8GB VRAM, CUDA 12.0+
- **Recommended**: NVIDIA RTX 4090 (16GB VRAM) for fastest generation
- **CPU**: Works but significantly slower

### Generation Speed

On NVIDIA RTX 4090:
- **Standard**: RTF ~0.30 (3x real-time)
- **With Nano-VLLM**: RTF ~0.13 (7.7x real-time)

## Advanced Features

### Voice Design

Create custom voices from text descriptions:

```python
from voxcpm import VoxCPM

model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)

# Voice design with text description
wav = model.generate(
    text="(A young woman, gentle and sweet voice)Hello, welcome to VoxCPM2!",
    cfg_value=2.0,
    inference_timesteps=10,
)
```

### Controllable Cloning

Clone a voice with style control:

```python
wav = model.generate(
    text="(slightly faster, cheerful tone)This is a cloned voice with style control.",
    reference_wav_path="path/to/voice.wav",
    cfg_value=2.0,
    inference_timesteps=10,
)
```

### Ultimate Cloning

Reproduce every vocal nuance with reference audio + transcript:

```python
wav = model.generate(
    text="This is an ultimate cloning demonstration.",
    prompt_wav_path="path/to/voice.wav",
    prompt_text="The transcript of the reference audio.",
    reference_wav_path="path/to/voice.wav",
)
```

### Streaming

Generate audio in chunks for real-time applications:

```python
chunks = []
for chunk in model.generate_streaming(text="Streaming text to speech is easy with VoxCPM!"):
    chunks.append(chunk)
```

## Troubleshooting

### Model Download Fails

```bash
# Try ModelScope (faster in China)
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('OpenBMB/VoxCPM2')"
```

### CUDA Version Mismatch

```bash
# Check CUDA version
nvcc --version

# Install compatible PyTorch
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

### Out of Memory

- Use a smaller model (VoxCPM1.5 or VoxCPM-0.5B)
- Reduce `inference_timesteps` in the VoxCPMTTS class
- Close other GPU applications

### Slow Generation

- Use Nano-VLLM for production deployment: `pip install nano-vllm-voxcpm`
- Use RTX 4090 or similar high-end GPU
- Reduce `inference_timesteps` parameter

## Resources

- **GitHub**: https://github.com/OpenBMB/VoxCPM
- **Hugging Face**: https://huggingface.co/openbmb/VoxCPM2
- **Documentation**: https://voxcpm.readthedocs.io/en/latest/
- **Demo Page**: https://openbmb.github.io/voxcpm2-demopage/
- **Technical Report**: https://arxiv.org/abs/2509.24650

## License

VoxCPM is released under the Apache-2.0 license, free for commercial use.

## References

- Zhou, Yixuan, et al. "VoxCPM: Tokenizer-Free TTS for Context-Aware Speech Generation and True-to-Life Voice Cloning." arXiv preprint arXiv:2509.24650, 2025.
