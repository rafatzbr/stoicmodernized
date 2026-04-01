from pathlib import Path

import pytest

from src.config import VideoMode
from src.stages.scenes import SceneStage
from src.stages.script import ScriptStage
from src.stages.subtitles import SubtitleStage


@pytest.mark.asyncio
async def test_short_mode_script_is_shorter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = ScriptStage(job_id="short-job", mock=True, video_mode=VideoMode.SHORT)
    result = await stage.run({"topic": "workplace stress", "title": "Workplace Stress"})

    assert "[0:50-0:58]" in result.narration
    assert len(result.chapters) == 4


@pytest.mark.asyncio
async def test_short_mode_scene_plan_stays_within_short_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    script_stage = ScriptStage(job_id="short-job", mock=True, video_mode=VideoMode.SHORT)
    script = await script_stage.run({"topic": "workplace stress", "title": "Workplace Stress"})

    scene_stage = SceneStage(job_id="short-job", mock=True)
    scene_plan = await scene_stage.run(script.model_dump(mode="json"))

    assert scene_plan.total_duration <= 60.0
    assert len(scene_plan.scenes) <= 6


@pytest.mark.asyncio
async def test_subtitles_use_audio_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = SubtitleStage(job_id="sub-job", mock=False)
    stage.job_dir = tmp_path / "jobs" / "sub-job"
    stage.subtitles_dir = stage.job_dir / "subtitles"

    stage._get_audio_duration = lambda _path: 12.0
    result = await stage.run(
        {"narration": "[0:00-0:10] Intro\nOne short line.\nAnother slightly longer line."},
        "dummy.mp3",
    )

    assert result.segments[-1].end_time == 12.0
    assert result.segments[0].start_time == 0.0
    assert len(result.segments) >= 2
    assert all(len(segment.text.split()) <= 6 for segment in result.segments)
