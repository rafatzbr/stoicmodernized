#!/usr/bin/env python3
"""Test script for VoxCPM TTS integration (CLI-based)."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.stages.tts import VoxCPMTTS


async def test_voxcpm():
    """Test VoxCPM TTS generation."""
    print("=" * 60)
    print("VoxCPM TTS Integration Test (CLI-based)")
    print("=" * 60)

    # Create output directory
    output_dir = Path(__file__).parent.parent / "output" / "test_voxcpm"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize VoxCPM
    tts = VoxCPMTTS(
        model_path=None,  # Will auto-detect
        voice="calm, deep male voice",  # Optional voice design
        speed=1.0,
    )

    # Test text
    test_text = "Welcome to Stoic Modernized. Today, we explore how Marcus Aurelius would handle a stressful day at work."

    # Generate audio
    output_path = output_dir / "test.wav"
    print(f"\nGenerating audio to: {output_path}")
    print(f"Text: {test_text}")
    print(f"Voice: {tts.voice}")
    print(f"Backend: {tts.backend}")
    print(f"Threads: {tts.threads}")

    try:
        result_path = await tts.generate_audio(test_text, output_path)
        print(f"\n✓ Success! Audio saved to: {result_path}")
        print(f"  File size: {result_path.stat().st_size / 1024:.1f} KB")
        print(f"  Sample rate: {tts.sample_rate} Hz")
        return True
    except RuntimeError as e:
        print(f"\n✗ Error: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_voxcpm())
    sys.exit(0 if success else 1)
