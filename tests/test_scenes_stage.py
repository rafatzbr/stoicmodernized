import json
from datetime import UTC, datetime
from pathlib import Path

from src.models import Scene, ScenePlan
from src.stages.scenes import SceneStage


def test_extract_steering_context_prefers_persisted_script_fields() -> None:
    stage = SceneStage(job_id="scene-job-1", mock=False)

    context = stage._extract_steering_context(
        {
            "steering_chain": {
                "ledger_packet": {"objective": "discovery"},
                "whiskers_handoff": {"viewer_problem": "meeting spiral"},
                "ledger_strategy": {"packaging_angle": "concrete pain first"},
            }
        }
    )

    assert context["ledger_packet"]["objective"] == "discovery"
    assert context["whiskers_handoff"]["viewer_problem"] == "meeting spiral"
    assert context["ledger_strategy"]["packaging_angle"] == "concrete pain first"


def test_save_scene_plan_persists_steering_context(tmp_path: Path) -> None:
    stage = SceneStage(job_id="scene-job-2", mock=False)
    stage.scenes_dir = tmp_path / "scenes"
    stage.scenes_dir.mkdir(parents=True, exist_ok=True)
    stage.last_steering_context = {
        "ledger_packet": {"objective": "conversion"},
        "whiskers_handoff": {"viewer_problem": "approval seeking at work"},
    }

    plan = ScenePlan(
        scenes=[
            Scene(
                scene_number=1,
                start_time=0.0,
                end_time=5.0,
                narration_segment="A worker stares at Slack before a meeting.",
                visual_prompt="office desk, anxious worker, slack glow, no text",
            )
        ],
        intro_duration=0.0,
        outro_duration=0.0,
        total_duration=5.0,
        topic="Work Anxiety",
    )

    path = stage.save_scene_plan(plan)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["steering_context"]["ledger_packet"]["objective"] == "conversion"
    assert payload["steering_context"]["whiskers_handoff"]["viewer_problem"] == "approval seeking at work"
