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


def test_detailed_scene_prompt_is_binding_source_of_truth() -> None:
    prompt = build_narrative_scene_prompt(
        subject="Why A Work Argument Ruins Your Night",
        scene_prompt=(
            "vertical 9:16 candid editorial photograph, worker sitting alone at a modern office desk "
            "in dim evening light, head resting on hand with a look of mental exhaustion, "
            "face-down smartphone on the desk, a capped pen, and a half-finished notebook, "
            "shallow depth of field, natural office lighting, no readable text, no logos, no watermark"
        ),
        narration_segment=(
            "You just walked away from a heated team argument, but your mind is still replaying every word. "
            "That tension is now following you into your dinner, your commute, and your sleep."
        ),
        overlay="Replay Loop",
        mode="over_shoulder",
        steering_hint="scenario cue: conflict follows home",
    )

    prompt_lower = prompt.lower()
    assert "specific stoic modernized workplace scene for: why a work argument ruins your night" in prompt_lower
    assert "depict exactly this scene" in prompt_lower
    assert "heated team argument" in prompt_lower
    assert "face-down smartphone" in prompt_lower
    assert "half-finished notebook" in prompt_lower
    assert "dim evening light" in prompt_lower
    assert "generic office" in prompt_lower
    assert "back seat of a rideshare" not in prompt_lower
    assert "conference table" not in prompt_lower


def test_specific_conflict_scene_does_not_trigger_approval_template() -> None:
    prompt = build_narrative_scene_prompt(
        subject="When a Work Conflict Follows You Home",
        scene_prompt=(
            "vertical 9:16 candid editorial photograph, professional standing in a quiet office hallway, "
            "eyes closed taking a slow breath, business casual shirt, blurred office corridor behind them, "
            "phone and access badge held at their side, no readable text, no logos, no watermark"
        ),
        narration_segment="To stop this cycle, practice a deliberate pause before you leave the office.",
        overlay="The Pause",
        mode="environment",
    )

    prompt_lower = prompt.lower()
    assert "quiet office hallway" in prompt_lower
    assert "access badge" in prompt_lower
    assert "before you leave the office" in prompt_lower
    assert "anonymous feedback" not in prompt_lower
    assert "long conference table" not in prompt_lower
