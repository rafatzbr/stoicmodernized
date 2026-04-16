"""Test Remotion video renderer."""

import asyncio
from pathlib import Path

from src.config import settings
from src.models import Scene, VideoRenderConfig, VideoRenderResult
from src.stages.remotion_renderer import RemotionVideoRenderer


async def test_remotion_renderer():
    """Test Remotion renderer with sample data."""
    
    # Create a test job
    job_id = "test-remotion-" + settings.job_id
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    
    # Create sample scenes
    scenes = [
        Scene(
            scene_number=1,
            start_time=0,
            end_time=5,
            subtitle="Fear of losing your job is keeping you from saying no...",
            animation_style="zoom",
        ),
        Scene(
            scene_number=2,
            start_time=5,
            end_time=10,
            subtitle="But overcommitting is what actually puts your career at risk.",
            animation_style="zoom",
        ),
        Scene(
            scene_number=3,
            start_time=10,
            end_time=15,
            subtitle="The core of Stoicism is the dichotomy of control.",
            animation_style="zoom",
        ),
    ]
    
    # Create render config
    config = VideoRenderConfig(
        scenes=scenes,
        audio_path="/home/rafatz/projects/stoic-modernized/output/jobs/e86be596-5d8a-40b1-bfbb-306db80378a2/audio/narration.wav",
        subtitle_path=None,
        output_path=str(settings.jobs_dir / job_id / "output" / "test.mp4"),
        width=1920,
        height=1080,
    )
    
    # Create renderer
    renderer = RemotionVideoRenderer(job_id)
    
    try:
        result = await renderer.render(config)
        print(f"✅ Remotion render successful!")
        print(f"   Video: {result.video_path}")
        print(f"   Duration: {result.duration}s")
        print(f"   Thumbnail: {result.thumbnail_path}")
    except Exception as e:
        print(f"❌ Remotion render failed: {e}")
        print("\nNext steps:")
        print("1. Check that Remotion is installed: npm install remotion")
        print("2. Test Remotion Studio: cd frontend && npm run remotion:dev")
        print("3. Verify Node.js version: node --version (need 16+)")


if __name__ == "__main__":
    asyncio.run(test_remotion_renderer())
