# VoxCPM TTS Integration Summary

## Changes Made

### 1. Core Code Changes

#### `src/config.py`
- Added `VOXCPM = "voxcpm"` to the `TTSProvider` enum

#### `src/stages/tts.py`
- **Replaced Python API implementation with CLI wrapper**
- Added `VoxCPMTTS` class with:
  - CLI-based execution using VoxCPM.cpp
  - Support for CPU, CUDA, and Vulkan backends
  - Voice design support (text-based voice descriptions)
  - Speed control (0.25x to 4.0x)
  - 48kHz audio output
  - Automatic model path detection
  - Error handling with clear installation instructions

#### `TTSStage` updates:
- Updated `_build_interface()` to handle "voxcpm" provider
- Updated `run()` to use .wav extension for VoxCPM

### 2. Configuration Files

#### `.env.example`
- Updated TTS_PROVIDER options documentation
- Added `TTS_SPEED` parameter (0.25 to 4.0)
- Added VoxCPM CLI configuration options:
  - `VOXCPM_MODEL_PATH` - Path to GGUF model
  - `VOXCPM_BACKEND` - cpu, cuda, vulkan, or auto
  - `VOXCPM_THREADS` - Number of CPU threads
  - `VOXCPM_QUANTIZATION` - Model quantization

#### `.env`
- Added `TTS_PROVIDER=local` (default)
- Added commented VoxCPM configuration examples

#### `pyproject.toml`
- Removed Python `voxcpm` dependency (now uses CLI)
- Updated optional-dependencies section to note CLI requirement

#### `README.md`
- Updated Configuration section to include VoxCPM options
- Added VoxCPM TTS usage documentation with CLI build instructions
- Updated Architecture section
- Added installation instructions for VoxCPM.cpp

#### `docs/VOXCPM_TTS.md` (UPDATED)
- Comprehensive VoxCPM.cpp documentation
- Build instructions for CPU/CUDA/Vulkan
- Model download instructions
- Configuration guide
- Voice design and cloning features
- Performance benchmarks
- Troubleshooting section

### 3. Test Files

#### `test_voxcpm.py` (UPDATED)
- Standalone test script for VoxCPM CLI integration
- Tests basic audio generation
- Validates output file and sample rate

## Usage

### Quick Start

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

# Configure
echo "TTS_PROVIDER=voxcpm" >> .env
echo "VOXCPM_MODEL_PATH=/home/rafatz/models/voxcpm/voxcpm1.5-q8_0-audiovae-f16.gguf" >> .env

# Run pipeline
python -m src.main run "your topic here"
```

## Key Features

1. **Multilingual Support**: 30 languages
2. **Voice Design**: Create voices from text descriptions
3. **48kHz Quality**: Studio-grade audio output
4. **Multiple Backends**: CPU, CUDA, or Vulkan
5. **Quantized Models**: Smaller, faster inference
6. **Clear Error Messages**: Helpful installation guidance

## Performance (from VoxCPM.cpp docs)

### CPU (i5-12600K, 8 threads)

| Model | Quant | RTF (full pipeline) | Size |
|-------|-------|---------------------|------|
| voxcpm-0.5b | Q4_K | 3.609 | 477 MB |
| voxcpm1.5 | Q8_0 | 4.291 | 942 MB |
| voxcpm1.5 | Q4_K+AV | 2.848 | 647 MB |

### CUDA (RTX 4060 Ti)

| Model | Quant | RTF (full pipeline) | Size |
|-------|-------|---------------------|------|
| voxcpm-0.5b | Q4_K | 0.550 | 477 MB |
| voxcpm1.5 | Q8_0+AV | 0.559 | 984 MB |

**RTF** = Real-Time Factor (lower is faster)

## Testing

```bash
# Run VoxCPM test
cd /home/rafatz/projects/stoic-modernized
.venv/bin/python test_voxcpm.py
```

## Next Steps

1. Build VoxCPM.cpp on your Vulkan/CPU machine
2. Download a model from Hugging Face
3. Test with a real pipeline run
4. Consider adding voice cloning support (reference audio)

## Files Modified

- `src/config.py`
- `src/stages/tts.py`
- `.env.example`
- `.env`
- `pyproject.toml`
- `README.md`

## Files Created

- `docs/VOXCPM_TTS.md`
- `test_voxcpm.py`
- `VOXCPM_INTEGRATION.md` (this file)

## Important Notes

- **No Python dependencies** - Uses external CLI tool
- **Model files** - Download from Hugging Face (~500MB - 1GB)
- **First run** - Will check for model and provide helpful error if not found
- **Backend selection** - Uses `auto` by default (auto-detects best backend)
- **Speed control** - Supports 0.25x to 4.0x (default: 1.0)

## Resources

- **VoxCPM.cpp**: https://github.com/bluryar/VoxCPM.cpp
- **Models**: https://huggingface.co/bluryar/VoxCPM-GGUF
- **Official VoxCPM**: https://github.com/OpenBMB/VoxCPM
