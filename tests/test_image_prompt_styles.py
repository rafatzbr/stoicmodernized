from src.stages.images import build_narrative_scene_prompt, build_scene_style_suffix


def test_build_narrative_scene_prompt_uses_contextual_scene_design() -> None:
    commute_prompt = build_narrative_scene_prompt(
        subject="leave work at work",
        scene_prompt="A lone commuter on a train heading home after a long day.",
        narration_segment="The ride home is where the noise finally falls away.",
        overlay="Leave work at work",
        mode="environment",
    )
    meeting_prompt = build_narrative_scene_prompt(
        subject="recover after difficult feedback",
        scene_prompt="A worker alone in a conference room after a hard meeting.",
        narration_segment="The meeting is over but the tension is still in the room.",
        overlay="After the meeting",
        mode="environment",
    )

    assert commute_prompt != meeting_prompt
    assert any(token in commute_prompt.lower() for token in ["train", "subway", "rideshare", "station", "city"])
    assert any(token in meeting_prompt.lower() for token in ["conference", "meeting", "glass", "chairs"])


def test_build_scene_style_suffix_is_deterministic_and_contextual() -> None:
    kwargs = {
        "subject": "protect your attention",
        "scene_prompt": "A phone is placed face-down before replying.",
        "narration_segment": "The worker decides not to react immediately.",
        "overlay": "Pause first",
        "mode": "object_only",
    }

    first = build_scene_style_suffix(**kwargs)
    second = build_scene_style_suffix(**kwargs)

    assert first == second
    assert "vertical 9:16" in first
    assert "no stock-photo smiles" in first
    assert any(
        fragment in first
        for fragment in [
            "symbolic insert shot",
            "tight composition around a few meaningful objects",
            "editorial still-life clarity",
            "high-end documentary texture",
        ]
    )
