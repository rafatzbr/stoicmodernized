import json
from pathlib import Path

import pytest

from src.stages.images import ImageGenerationError, ImageGenerationStage, build_narrative_scene_prompt


def test_build_narrative_scene_prompt_appends_steering_hint() -> None:
    prompt = build_narrative_scene_prompt(
        subject="work anxiety",
        scene_prompt="worker alone after a difficult meeting",
        narration_segment="The meeting is over but your body is still acting like it is happening.",
        overlay="After The Meeting",
        mode="environment",
        steering_hint="packaging angle: identity-level anxiety | lane: conversion",
    )

    assert "packaging angle: identity-level anxiety" in prompt
    assert "lane: conversion" in prompt


@pytest.mark.asyncio
async def test_placeholder_images_include_steering_hint_in_prompt(tmp_path: Path) -> None:
    stage = ImageGenerationStage(job_id="img-job-1", mock=False, placeholder_only=True)
    stage.images_dir = tmp_path / "images"
    stage.images_dir.mkdir(parents=True, exist_ok=True)

    scene_plan = {
        "topic": "Work Anxiety",
        "steering_context": {
            "ledger_packet": {"objective": "conversion", "packaging_angle": "identity-level anxiety"},
            "whiskers_handoff": {"viewer_problem": "spiraling after meetings", "stoic_move": "separate judgment from event"},
            "ledger_strategy": {},
            "whiskers_brief": {},
        },
        "scenes": [
            {
                "scene_number": 1,
                "visual_prompt": "worker alone in a quiet conference room",
                "narration_segment": "The meeting is over but your body is still acting like it is happening.",
                "text_overlay": "After The Meeting",
            }
        ],
    }

    assets = await stage._generate_placeholder_images(scene_plan)

    assert "steering:" in assets[0].prompt
    assert "identity-level anxiety" in assets[0].prompt
    assert "spiraling after meetings" in assets[0].prompt


def test_save_assets_persists_steering_context(tmp_path: Path) -> None:
    stage = ImageGenerationStage(job_id="img-job-2", mock=False, placeholder_only=True)
    stage.images_dir = tmp_path / "images"
    stage.images_dir.mkdir(parents=True, exist_ok=True)
    stage.last_steering_context = {
        "ledger_packet": {"objective": "discovery"},
        "whiskers_handoff": {"viewer_problem": "slack distraction"},
    }

    from src.models import ImageAsset

    path = stage.save_assets([
        ImageAsset(scene_number=1, image_path="/tmp/scene_001.jpg", prompt="prompt", seed=1)
    ])
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["steering_context"]["ledger_packet"]["objective"] == "discovery"
    assert payload["steering_context"]["whiskers_handoff"]["viewer_problem"] == "slack distraction"


@pytest.mark.asyncio
async def test_real_run_blocks_placeholder_images_without_explicit_override() -> None:
    stage = ImageGenerationStage(job_id="img-job-3", mock=False, placeholder_only=True)

    with pytest.raises(ImageGenerationError, match="placeholder_images_forbidden"):
        await stage.run({"topic": "Work Anxiety", "scenes": [{"scene_number": 1, "visual_prompt": "worker at desk"}]})
