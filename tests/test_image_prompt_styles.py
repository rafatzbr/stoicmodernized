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
            "desk-level documentary close-up",
            "foreground-background separation",
            "candid tension carried by the objects",
            "high-end documentary texture",
        ]
    )


def test_approval_pressure_prompt_is_specific_not_generic() -> None:
    prompt = build_narrative_scene_prompt(
        subject="You Do Not Need Everyone at Work to Like You",
        scene_prompt="approval pressure after disagreement",
        narration_segment="Finance wants cost efficiency and marketing wants responsiveness; disagreement is not personal.",
        overlay="Not Personal",
        mode="person_medium",
        steering_hint="overlay cue: Not Personal",
    )

    prompt_lower = prompt.lower()
    assert "conference table" in prompt_lower or "glass meeting room" in prompt_lower
    assert any(token in prompt_lower for token in ["pen gripped", "phone face-down", "blank whiteboard"])
    banned = [
        "modern office professional",
        "grounded contemporary office",
        "emotionally specific action",
        "small symbolic props",
        "workplace context:",
        "still-life object shot",
        "symbolic insert shot",
    ]
    assert not any(phrase in prompt_lower for phrase in banned)
