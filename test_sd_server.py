#!/usr/bin/env python3
"""Quick test script for SD server image generation."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.stages.images import SdServerImageGeneration


async def test_sd_server():
    """Test SD server image generation."""
    print("=" * 60)
    print("SD Server Image Generation Test")
    print("=" * 60)

    # Create test job directory
    job_id = "test_sd_server"
    job_dir = Path(__file__).parent.parent / "output" / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Create a test scene plan
    scene_plan = {
        "topic": "test topic",
        "scenes": [
            {
                "scene_number": 1,
                "visual_prompt": "test scene",
                "text_overlay": "Test overlay",
            }
        ]
    }

    # Initialize SD server generation
    sd_gen = SdServerImageGeneration(job_id=job_id, mock=False)

    # Check if server is available
    if not sd_gen._server_available():
        print("✗ SD server not available!")
        return False

    print(f"✓ SD server available at {sd_gen.sd_server_url}")

    # Test image generation
    try:
        print("\nGenerating test image...")
        assets = await sd_gen.generate(scene_plan)

        if assets:
            print(f"\n✓ Success! Generated {len(assets)} image(s)")
            for asset in assets:
                image_path = Path(asset.image_path)
                print(f"  - {image_path}")
                if image_path.exists():
                    print(f"    Size: {image_path.stat().st_size / 1024:.1f} KB")
                else:
                    print(f"    ✗ File not found!")
                print(f"    Prompt: {asset.prompt[:100]}...")
            return True
        else:
            print("✗ No images generated")
            return False
    except Exception as e:
        print(f"\n✗ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_sd_server())
    sys.exit(0 if success else 1)
