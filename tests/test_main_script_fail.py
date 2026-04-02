from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.main import app
from src.models import ResearchResult, ResearchSource
from src.stages.script import ScriptGenerationError


runner = CliRunner()


def test_script_command_marks_job_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
    job_dir = tmp_path / "jobs" / job.job_id / "research"
    job_dir.mkdir(parents=True, exist_ok=True)
    research_path = job_dir / "research.json"
    research_path.write_text(
        '{"topic":"handling workplace stress","title":"Handling Workplace Stress: A Stoic Perspective","sources":[],"key_insights":[],"workplace_applications":[]}',
        encoding="utf-8",
    )
    test_db.update_job(job.job_id, status="research_complete", research_path=str(research_path))

    async def fake_run(self, _research_data):
        raise ScriptGenerationError("local_llm_returned_empty_content")

    monkeypatch.setattr(main_module.ScriptStage, "run", fake_run)

    result = runner.invoke(app, ["script", job.job_id, "--video-mode", "short"])

    refreshed = test_db.get_job(job.job_id)
    assert result.exit_code == 1
    assert "Script Generation Failed!" in result.stdout
    assert "local_llm_returned_empty_content" in result.stdout
    assert refreshed.status == "script_failed"
    assert refreshed.error_message == "local_llm_returned_empty_content"


def test_run_stops_after_failed_script(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    from src.database import Database
    import src.main as main_module
    import src.database as database_module

    test_db = Database()
    database_module.db = test_db
    main_module.db = test_db

    def fake_research(*args, **kwargs):
        topic = kwargs.get("topic") or args[0]
        job_id = kwargs.get("job_id")
        if job_id is None:
            raise AssertionError("expected run() to create a job before research")
        research_dir = tmp_path / "jobs" / job_id / "research"
        research_dir.mkdir(parents=True, exist_ok=True)
        research_path = research_dir / "research.json"
        research_path.write_text(
            '{"topic":"' + topic + '","title":"Handling Workplace Stress: A Stoic Perspective","sources":[],"key_insights":[],"workplace_applications":[]}',
            encoding="utf-8",
        )
        test_db.update_job(job_id, status="research_complete", research_path=str(research_path))

    def fake_script(*args, **kwargs):
        job_id = kwargs.get("job_id") or args[0]
        test_db.update_job(job_id, status="script_failed", error_message="local_llm_payload_wrong_section_count")
        raise SystemExit(1)

    def should_not_run(*args, **kwargs):
        raise AssertionError("later pipeline stage should not run after script failure")

    monkeypatch.setattr(main_module, "research", fake_research)
    monkeypatch.setattr(main_module, "script", fake_script)
    monkeypatch.setattr(main_module, "scene", should_not_run)
    monkeypatch.setattr(main_module, "tts", should_not_run)
    monkeypatch.setattr(main_module, "images", should_not_run)
    monkeypatch.setattr(main_module, "subtitles", should_not_run)
    monkeypatch.setattr(main_module, "render", should_not_run)
    monkeypatch.setattr(main_module, "metadata", should_not_run)
    monkeypatch.setattr(main_module, "upload", should_not_run)

    result = runner.invoke(app, ["run", "handling workplace stress", "--skip-upload", "--video-mode", "short"])

    jobs = [job for job in test_db.get_all_jobs() if job.topic == "handling workplace stress"]
    assert result.exit_code == 1
    assert jobs
    latest = max(jobs, key=lambda job: job.created_at)
    assert latest.status == "script_failed"
    assert latest.error_message == "local_llm_payload_wrong_section_count"
