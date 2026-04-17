#!/usr/bin/env python3
"""Debug script to test TTS with VoxCPM."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.stages.tts import TTSStage


async def test_voxcpm_tts():
    """Test VoxCPM TTS generation."""
    print("=" * 60)
    print("VoxCPM TTS Debug Test")
    print("=" * 60)

    # Create test job directory
    job_id = "test_voxcpm_debug"
    job_dir = Path(__file__).parent.parent / "output" / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Create a test scene plan with actual narration text
    scene_plan = {
        "topic": "test",
        "scenes": [
            {
                "scene_number": 1,
                "narration_segment": "Welcome to Stoic Modernized. Today we explore how to handle workplace stress with wisdom.",
                "text_overlay": "Handling Stress",
                "visual_prompt": "professional at desk",
            }
        ]
    }

    # Initialize TTS stage with VoxCPM
    tts_stage = TTSStage(job_id=job_id, mock=False)
    print(f"\nTTS Provider (before): {tts_stage.provider}")
    
    # Force voxcpm provider
    tts_stage.provider = "voxcpm"
    tts_stage._audio_interface = None  # Reset interface
    tts_stage._build_interface("voxcpm")
    
    print(f"TTS Interface: {type(tts_stage.audio_interface).__name__}")

    print(f"\nTTS Provider: {tts_stage.provider}")
    print(f"Audio Dir: {tts_stage.audio_dir}")

    try:
        # Run TTS generation
        print("\nStarting TTS generation...")
        
        # Prepare narration text (same as TTSStage does)
        narration_segments = [
            scene.get("narration_segment", "")
            for scene in scene_plan.get("scenes", [])
            if scene.get("narration_segment")
            and scene.get("narration_segment") not in {"Intro branding", "Outro branding"}
        ]
        all_text = " ".join(narration_segments).strip() or "Stoic Modernized"
        print(f"Narration text: {all_text[:100]}...")
        
        audio_path = await tts_stage.run(scene_plan)

        if audio_path:
            print(f"\n✓ Success! Generated audio file:")
            print(f"  - {audio_path}")
            if audio_path.exists():
                import subprocess
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1", str(audio_path)],
                    capture_output=True,
                    text=True
                )
                duration = float(result.stdout.strip())
                print(f"    Duration: {duration:.2f} seconds")
                print(f"    Size: {audio_path.stat().st_size / 1024:.1f} KB")
            else:
                print(f"    ✗ File not found!")
            return True
        else:
            print("✗ No audio generated")
            return False
    except Exception as e:
        print(f"\n✗ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_voxcpm_tts())
    sys.exit(0 if success else 1)
