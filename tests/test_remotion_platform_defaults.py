from pathlib import Path

from src.config import Channel
from src.main import _default_remotion_platform
from src.stages.remotion_renderer import RemotionRenderer


def test_stoic_portrait_defaults_to_youtube_platform():
    assert _default_remotion_platform("portrait", Channel.STOIC_MODERNIZED) == "youtube"


def test_landscape_defaults_to_youtube_platform():
    assert _default_remotion_platform("landscape", Channel.STOIC_MODERNIZED) == "youtube"


def test_renderer_uses_youtube_platform_for_stoic_portrait_jobs():
    renderer = RemotionRenderer(
        job_id="test-job",
        frontend_dir=Path("/tmp/frontend"),
        mode="portrait",
        channel=Channel.STOIC_MODERNIZED,
    )

    assert renderer.platform == "youtube"
