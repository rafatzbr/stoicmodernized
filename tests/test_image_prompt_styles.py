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
    assert any(token in prompt_lower for token in ["conference room", "stairwell", "elevator lobby", "office kitchenette"])
    assert any(token in prompt_lower for token in ["coffee untouched", "phone lowered", "blank whiteboard", "access badge"])
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


def test_stoic_prompts_vary_by_modern_work_beat_and_location() -> None:
    prompts = [
        build_narrative_scene_prompt(
            subject="Your Phone Is Stealing Your First Work Block",
            scene_prompt="attention notification pressure",
            narration_segment="Your phone pings before the workday starts and your attention is gone.",
            overlay="Attention Theft",
            mode="environment",
        ),
        build_narrative_scene_prompt(
            subject="You Do Not Need Everyone At Work To Like You",
            scene_prompt="approval pressure after disagreement",
            narration_segment="The urge to chase respect after disagreement drains your energy.",
            overlay="Approval Pressure",
            mode="person_medium",
        ),
        build_narrative_scene_prompt(
            subject="When A Work Conflict Follows You Home",
            scene_prompt="meeting replay anxiety",
            narration_segment="Your mind starts replaying the meeting in your head at night.",
            overlay="Replay Loop",
            mode="over_shoulder",
        ),
        build_narrative_scene_prompt(
            subject="Leave Work At Work",
            scene_prompt="after hours boundary shut down",
            narration_segment="Choose a boundary before the office follows you home.",
            overlay="Boundary",
            mode="hands_only",
        ),
    ]

    joined = "\n".join(prompts).lower()
    assert len(set(prompts)) == len(prompts)
    assert "stoic modernized modern-work anxiety scene" in joined
    assert "varied real-world location" in joined
    assert any(token in joined for token in ["bus stop", "kitchen counter", "entryway", "library table"])
    assert any(token in joined for token in ["stairwell", "elevator lobby", "parking garage", "front door threshold", "office kitchenette", "laundry room"])

    generic_hits = sum(joined.count(token) for token in ["modern office desk", "home workspace", "sitting alone with a laptop and notebook"])
    assert generic_hits == 0


def test_stoic_prompt_topics_choose_different_visual_worlds() -> None:
    attention = build_narrative_scene_prompt(
        subject="Your Phone Is Stealing Your First Work Block",
        scene_prompt="notification attention theft before work",
        narration_segment="Your phone pings before your first work block.",
        overlay="Phone Boundary",
        mode="environment",
    ).lower()
    boundary = build_narrative_scene_prompt(
        subject="Leave Work At Work",
        scene_prompt="after hours boundary shut down",
        narration_segment="Choose a boundary before the office follows you home.",
        overlay="Leave Work",
        mode="environment",
    ).lower()

    assert any(token in attention for token in ["bus stop", "kitchen counter", "apartment entryway", "library table"])
    assert any(token in boundary for token in ["elevator bank", "apartment doorway", "laundry room", "front door threshold"])
    assert attention != boundary


def test_data_request_prompt_uses_missing_range_visual_world_not_attention_fallback() -> None:
    prompt = build_narrative_scene_prompt(
        subject="Missing Range Clean Request",
        scene_prompt="ask before digging",
        narration_segment="A data request comes in missing the source date range. The urge to guess creates chaos. Stop.",
        overlay="Missing Range",
        mode="hands_only",
        steering_hint="scenario cue: A modern worker feels pressure but keeps giving that pressure control over attention and judgment.",
    ).lower()

    assert any(token in prompt for token in ["data request", "date-range", "calendar", "source report", "request folder"])
    assert "bus stop" not in prompt
    assert "phone glowing" not in prompt
    assert "home workspace near a window" not in prompt


def test_operational_scenario_cue_attention_does_not_override_concrete_data_request() -> None:
    prompt = build_narrative_scene_prompt(
        subject="When the Source Date Range Is Missing from the Data Request",
        scene_prompt="ask before digging",
        narration_segment="Clarify the exact attributes needed before any transfer.",
        overlay="Ask Before Digging",
        mode="environment",
        steering_hint="scenario cue: pressure control over attention and judgment",
    ).lower()

    assert any(token in prompt for token in ["date-range", "source report", "calendar", "request folder", "data request"])
    assert "home workspace near a window" not in prompt
    assert "bus stop" not in prompt


def test_fomo_and_conflict_topics_get_specific_visual_worlds_not_generic_desks() -> None:
    fomo = build_narrative_scene_prompt(
        subject="When Career FOMO Makes the Status Update Feel Like a Verdict",
        scene_prompt="career comparison fomo after colleague promotion announcement",
        narration_segment="A colleague posts a promotion and your own status update suddenly feels like proof you are behind.",
        overlay="Career FOMO",
        mode="environment",
    ).lower()
    conflict = build_narrative_scene_prompt(
        subject="When a Work Conflict Follows You Home",
        scene_prompt="passive-aggressive coworker conflict after meeting",
        narration_segment="The argument is over, but you keep rehearsing what you should have said.",
        overlay="Work Conflict",
        mode="person_medium",
    ).lower()

    assert any(token in fomo for token in ["cafe table", "promotion announcement", "library table", "stairwell"])
    assert any(token in conflict for token in ["glass meeting room", "office kitchenette", "stairwell", "elevator lobby"])
    assert "home workspace near a window" not in fomo
    assert "home workspace near a window" not in conflict
    assert "modern office desk" not in fomo
    assert fomo != conflict


def test_layoff_reorg_topic_gets_job_security_visual_world() -> None:
    prompt = build_narrative_scene_prompt(
        subject="When Layoff Rumors Make Every Message Feel Dangerous",
        scene_prompt="reorg job security anxiety after budget cut rumor",
        narration_segment="Every calendar invite starts to look like a verdict on your job security.",
        overlay="Job Security",
        mode="over_shoulder",
    ).lower()

    assert any(token in prompt for token in ["reorg", "layoff", "job security", "budget", "parking garage", "closed conference room"])
    assert "home workspace near a window" not in prompt
