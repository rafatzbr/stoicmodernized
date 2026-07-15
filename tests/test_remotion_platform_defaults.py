from pathlib import Path
import json

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


def test_renderer_end_card_uses_script_cta_variant(tmp_path: Path):
    renderer = RemotionRenderer(
        job_id="test-job",
        frontend_dir=tmp_path / "frontend",
        mode="portrait",
        channel=Channel.STOIC_MODERNIZED,
    )
    renderer.job_dir = tmp_path / "job"
    (renderer.job_dir / "script").mkdir(parents=True)
    (renderer.job_dir / "script" / "script.json").write_text(
        json.dumps({"title": "Work Pressure", "cta": "Subscribe to @stoic-modernized for sharper judgment under office pressure."})
    )

    props = renderer._generate_props(
        [{"scene_number": 1, "start_time": 0, "end_time": 5, "narration_segment": "line"}],
        [],
        "audio/narration.mp3",
        None,
    )

    assert props["ctaText"] == "For sharper judgment under office pressure."
