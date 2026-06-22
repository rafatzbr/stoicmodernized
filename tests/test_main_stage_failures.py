import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from src.main import app


runner = CliRunner()


def _isolated_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    from src.database import Database
    import src.database as database_module
    import src.main as main_module

    test_db = Database()
    database_module.db = test_db
    main_module.db = test_db
    return test_db


def test_tts_command_marks_job_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    test_db = _isolated_db(monkeypatch, tmp_path)

    job = test_db.create_job("handling workplace stress")
    scenes_dir = tmp_path / "jobs" / job.job_id / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    scene_path = scenes_dir / "scenes.json"
    scene_path.write_text('{"scenes":[]}', encoding="utf-8")
    test_db.update_job(job.job_id, status="scene_complete", scene_plan_path=str(scene_path))

    import src.main as main_module

    async def fake_run(self, _scene_plan):
        raise RuntimeError("tts provider unavailable")

    monkeypatch.setattr(main_module.TTSStage, "run", fake_run)

    result = runner.invoke(app, ["tts", job.job_id])

    refreshed = test_db.get_job(job.job_id)
    assert result.exit_code == 1
    assert "TTS Failed!" in result.stdout
    assert refreshed.status == "tts_failed"
    assert refreshed.error_message == "tts provider unavailable"


def test_music_command_marks_job_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    test_db = _isolated_db(monkeypatch, tmp_path)

    job = test_db.create_job("handling workplace stress")

    import src.main as main_module

    async def fake_run(self, **_kwargs):
        raise RuntimeError("no approved tracks")

    monkeypatch.setattr(main_module.BackgroundMusicStage, "run", fake_run)

    result = runner.invoke(app, ["music", job.job_id])

    refreshed = test_db.get_job(job.job_id)
    assert result.exit_code == 1
    assert "Background Music Failed!" in result.stdout
    assert refreshed.status == "music_failed"
    assert refreshed.error_message == "no approved tracks"


def test_render_precondition_marks_job_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    test_db = _isolated_db(monkeypatch, tmp_path)

    job = test_db.create_job("handling workplace stress")

    result = runner.invoke(app, ["render", job.job_id])

    refreshed = test_db.get_job(job.job_id)
    assert result.exit_code == 1
    assert "Render Failed!" in result.stdout
    assert refreshed.status == "render_failed"
    assert refreshed.error_message == "No scene plan found. Run scene stage first."


def test_mock_metadata_payload_does_not_send_script_text_to_ai(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.main as main_module

    script_path = tmp_path / "script.json"
    script_path.write_text(
        json.dumps(
            {
                "title": "When the Spreadsheet Formula Changes the Total",
                "narration": "This narration would trigger AI description generation.",
                "chapters": [{"title": "Hook", "timestamp": 0}],
            }
        ),
        encoding="utf-8",
    )
    job_record = SimpleNamespace(script_path=str(script_path))
    seen: dict[str, object] = {}

    def fake_generate_metadata(self, **kwargs):
        seen.update(kwargs)
        return {"title": kwargs["script_title"], "description": "fallback", "tags": [], "chapters": []}

    monkeypatch.setattr(main_module.YouTubeUploader, "generate_metadata", fake_generate_metadata)

    payload = main_module._generate_metadata_payload_for_job("job-1", job_record, mock=True)

    assert payload["description"] == "fallback"
    assert seen["script_text"] is None
