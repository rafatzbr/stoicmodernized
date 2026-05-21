from pathlib import Path

from src.ledger_strategy import LedgerStrategyManager


def test_load_topic_ideas_reads_and_refreshes_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    artifacts = workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "stoic-modernized-council-plan-2026-05-10.md").write_text(
        "# Plan\n- 4 discovery videos\n- 3 conversion videos\n",
        encoding="utf-8",
    )

    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)

    payload = manager.load_topic_plan(niche="modern work")

    assert manager.topic_plan_path.exists()
    assert manager.topic_ideas_path.exists()
    assert payload["niche"] == "modern work"
    assert payload["batches"]["discovery"][0]["objective"] == "discovery"
    assert payload["strategy_generated_at"]

    cached = manager.load_topic_plan(niche="modern work")
    assert cached["generated_at"] == payload["generated_at"]


def test_build_job_packet_includes_steering_fields(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
    manager = LedgerStrategyManager(project_root=tmp_path, workspace_root=workspace)

    from src.config import Channel, VideoMode

    packet = manager.build_job_packet(
        job_id="job-123",
        topic="work anxiety",
        channel=Channel.STOIC_MODERNIZED,
        video_mode=VideoMode.SHORT,
    )

    assert packet["objective"] == "conversion"
    assert packet["packaging_angle"]
    assert packet["title_formulas"]
    assert packet["avoid_angles"]
    assert packet["experiment_hypothesis"]
