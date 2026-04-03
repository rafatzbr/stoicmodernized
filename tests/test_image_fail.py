from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.main import app
from src.stages.images import ImageGenerationError, ImageGenerationStage


runner = CliRunner()


@pytest.mark.asyncio
async def test_real_image_generation_raises_instead_of_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = ImageGenerationStage(job_id="img-fail", mock=False, placeholder_only=False)
    stage.job_dir = tmp_path / "jobs" / "img-fail"
    stage.images_dir = stage.job_dir / "images"
    stage._sd_cli_available = lambda: True  # type: ignore[method-assign]

    async def fail_generate_single_image(**_: object) -> None:
        raise RuntimeError("boom")

    stage._generate_single_image = fail_generate_single_image  # type: ignore[method-assign]

    with pytest.raises(ImageGenerationError, match="image_generation_failed_for_scene_1"):
        await stage.run(
            {
                "topic": "test topic",
                "scenes": [
                    {
                        "scene_number": 1,
                        "visual_prompt": "specific visual",
                        "text_overlay": "Test",
                    }
                ],
            }
        )


def test_images_command_marks_job_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    from src.database import Database
    import src.main as main_module
    import src.database as database_module

    test_db = Database()
    database_module.db = test_db
    main_module.db = test_db

    job = test_db.create_job("handling workplace stress")
    scenes_dir = tmp_path / "jobs" / job.job_id / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    scene_path = scenes_dir / "scenes.json"
    scene_path.write_text(
        '{"scenes":[{"scene_number":1,"start_time":0.0,"end_time":5.0,"narration_segment":"Test line","visual_prompt":"visual","text_overlay":"Test"}]}',
        encoding="utf-8",
    )
    test_db.update_job(job.job_id, status="scene_complete", scene_plan_path=str(scene_path))

    async def fake_run(self, _scene_plan):
        raise ImageGenerationError("image_generation_failed_for_scene_1: RuntimeError: boom")

    monkeypatch.setattr(main_module.ImageGenerationStage, "run", fake_run)

    result = runner.invoke(app, ["images", job.job_id])

    refreshed = test_db.get_job(job.job_id)
    assert result.exit_code == 1
    assert "Image Generation Failed!" in result.stdout
    assert "image_generation_failed_for_scene_1" in result.stdout
    assert refreshed.status == "images_failed"
    assert refreshed.error_message == "image_generation_failed_for_scene_1: RuntimeError: boom"



def test_sd_cli_log_is_appended_per_image_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    import subprocess

    stage = ImageGenerationStage(job_id="img-log", mock=False, placeholder_only=False)
    stage.job_dir = tmp_path / "jobs" / "img-log"
    stage.images_dir = stage.job_dir / "images"
    stage.sd_log_path = stage.images_dir / "sd-cli.log"
    stage.images_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.CompletedProcess(
        args=["sd"],
        returncode=0,
        stdout="ok output",
        stderr="warn output",
    )
    stage._append_sd_cli_log(
        output_path=stage.images_dir / "scene_001.jpg",
        command=["sd", "-p", "prompt", "-n", "text, logo"],
        result=result,
    )

    log_text = stage.sd_log_path.read_text(encoding="utf-8")
    assert "output_image:" in log_text
    assert "scene_001.jpg" in log_text
    assert "command:" in log_text
    assert "sd -p prompt -n 'text, logo'" in log_text
    assert "stdout:" in log_text and "ok output" in log_text
    assert "stderr:" in log_text and "warn output" in log_text



@pytest.mark.asyncio
async def test_sd_cli_assert_failure_retries_with_safe_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = ImageGenerationStage(job_id="img-retry", mock=False, placeholder_only=False)
    stage.job_dir = tmp_path / "jobs" / "img-retry"
    stage.images_dir = stage.job_dir / "images"
    stage.sd_log_path = stage.images_dir / "sd-cli.log"
    stage.images_dir.mkdir(parents=True, exist_ok=True)

    calls = []

    def fake_run(cmd, capture_output, text):
        calls.append(cmd)
        class Result:
            def __init__(self, returncode, stdout, stderr):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr
        if len(calls) == 1:
            return Result(-6, "", "GGML_ASSERT(i01 >= 0 && i01 < ne01) failed")
        return Result(0, "ok", "")

    monkeypatch.setattr('src.stages.images.subprocess.run', fake_run)

    await stage._generate_single_image(
        prompt="Long natural language prompt",
        output_path=stage.images_dir / "scene_001.jpg",
        negative_prompt="text, logo",
        subject="Work boundaries",
        scene_prompt="Focused worker closing laptop at a clean desk.",
        overlay="Leave on time",
    )

    assert len(calls) == 2
    assert '--steps' in calls[0] and '--steps' in calls[1]
    assert '40' in calls[0]
    assert '32' in calls[1]
    log_text = stage.sd_log_path.read_text(encoding='utf-8')
    assert log_text.count('command:') == 2
