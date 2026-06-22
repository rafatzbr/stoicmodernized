from pathlib import Path

from src.config import Channel
from src.stages.upload import YouTubeUploader


def _artifact(tmp_path: Path, job_id: str, title: str) -> tuple[Path, dict]:
    metadata_dir = tmp_path / job_id / "metadata"
    metadata_dir.mkdir(parents=True)
    path = metadata_dir / "metadata.json"
    path.write_text('{"title": "' + title + '"}', encoding="utf-8")
    return path, {"title": title}


def test_umbrella_balance_ignores_failed_recovery_attempts(monkeypatch, tmp_path):
    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    current_dir = tmp_path / "current"
    current_dir.mkdir()
    artifacts = [
        _artifact(tmp_path, "failed-one", "Why Rushing Breaks Builds When Cache Clears"),
        _artifact(tmp_path, "failed-two", "Stop Checklist Panic Before You Rush"),
    ]

    monkeypatch.setattr(uploader, "_job_matches_channel", lambda job_dir: True)
    monkeypatch.setattr(uploader, "_recent_subject_window_hit", lambda path, metadata: True)
    monkeypatch.setattr(uploader, "_job_status_for_dir", lambda job_dir: "script_blocked")

    error = uploader._umbrella_balance_guardrail(
        {"pressure", "meeting"},
        artifacts,
        current_dir,
        "Upload",
    )

    assert error is None


def test_umbrella_balance_still_counts_publishable_recent_artifacts(monkeypatch, tmp_path):
    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    current_dir = tmp_path / "current"
    current_dir.mkdir()
    artifacts = [
        _artifact(tmp_path, "published-one", "Office Pressure in the Morning Meeting"),
        _artifact(tmp_path, "published-two", "Meeting Pressure Before the Deadline"),
    ]

    monkeypatch.setattr(uploader, "_job_matches_channel", lambda job_dir: True)
    monkeypatch.setattr(uploader, "_recent_subject_window_hit", lambda path, metadata: True)
    monkeypatch.setattr(uploader, "_job_status_for_dir", lambda job_dir: "metadata_complete")

    error = uploader._umbrella_balance_guardrail(
        {"pressure", "meeting"},
        artifacts,
        current_dir,
        "Upload",
    )

    assert error is not None
    assert "subject-umbrella balance guardrail" in error
