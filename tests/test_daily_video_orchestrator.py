import importlib.util
import subprocess
from pathlib import Path


def load_daily_orchestrator():
    script_path = Path("/home/rafatz/.hermes/scripts/stoic-modernized-daily-video.py")
    spec = importlib.util.spec_from_file_location("stoic_daily_orchestrator", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_daily_orchestrator_asks_whiskers_for_new_subject_after_script_guardrail(monkeypatch, tmp_path):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "RUN_DIR", tmp_path)
    agent_dir = tmp_path / "agent-notes"
    agent_dir.mkdir()
    monkeypatch.setattr(orchestrator, "AGENT_DIR", agent_dir)

    commands: list[list[str]] = []
    asked_prompts: list[str] = []

    def fake_agent(profile, prompt, note_name, *, timeout=orchestrator.AGENT_TIMEOUT):
        asked_prompts.append(prompt)
        if "new Stoic Modernized video subject" in prompt:
            return "Handle Interruptions Without Losing Your Place"
        return "PASS"

    def fake_run_cmd(args, *, timeout, env=None, check=True):
        commands.append(list(args))
        stage = args[3]
        topic_or_job = args[4]
        if stage == "research":
            job_id = "job-rejected" if topic_or_job == "How to Stay Calm When Your Boss Changes Priorities" else "job-accepted"
            return subprocess.CompletedProcess(args, 0, stdout=f"Job ID: {job_id}\n", stderr=None)
        if stage == "script" and topic_or_job == "job-rejected":
            return subprocess.CompletedProcess(
                args,
                1,
                stdout=(
                    "Script Subject Validation Failed!\n"
                    "Reason: Upload blocked by same-month subject guardrail. "
                    "Regenerate with a different workplace trigger before publishing.\n"
                ),
                stderr=None,
            )
        if stage == "script" and topic_or_job == "job-accepted":
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)

    job_id, accepted_topic = orchestrator.research_and_script_with_subject_retries(
        "How to Stay Calm When Your Boss Changes Priorities",
        {
            "ideas": [
                {"title": "How to Stay Calm When Your Boss Changes Priorities"},
                {"title": "Handle Interruptions Without Losing Your Place"},
            ]
        },
    )

    assert job_id == "job-accepted"
    assert accepted_topic == "Handle Interruptions Without Losing Your Place"
    assert any("same-month subject guardrail" in prompt for prompt in asked_prompts)
    assert any("new Stoic Modernized video subject" in prompt for prompt in asked_prompts)
    assert [cmd[3:5] for cmd in commands] == [
        ["research", "How to Stay Calm When Your Boss Changes Priorities"],
        ["script", "job-rejected"],
        ["research", "Handle Interruptions Without Losing Your Place"],
        ["script", "job-accepted"],
    ]
    assert (agent_dir / "04-whiskers-subject-retry-1.md").exists()


def test_daily_orchestrator_keeps_valid_fresh_whiskers_retry_topic_outside_ledger(monkeypatch, tmp_path):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "RUN_DIR", tmp_path)
    agent_dir = tmp_path / "agent-notes"
    agent_dir.mkdir()
    monkeypatch.setattr(orchestrator, "AGENT_DIR", agent_dir)

    commands: list[list[str]] = []

    def fake_agent(profile, prompt, note_name, *, timeout=orchestrator.AGENT_TIMEOUT):
        if "new Stoic Modernized video subject" in prompt:
            return "How to Stay Calm When a Client Questions Your Work"
        return "PASS"

    def fake_run_cmd(args, *, timeout, env=None, check=True):
        commands.append(list(args))
        stage = args[3]
        topic_or_job = args[4]
        if stage == "research":
            job_id = "job-rejected" if topic_or_job == "How to Stay Calm When Your Boss Changes Priorities" else "job-accepted"
            return subprocess.CompletedProcess(args, 0, stdout=f"Job ID: {job_id}\n", stderr=None)
        if stage == "script" and topic_or_job == "job-rejected":
            return subprocess.CompletedProcess(
                args,
                1,
                stdout=(
                    "Script Subject Validation Failed!\n"
                    "Reason: Upload blocked by same-month subject guardrail. "
                    "Regenerate with a different workplace trigger before publishing.\n"
                ),
                stderr=None,
            )
        if stage == "script" and topic_or_job == "job-accepted":
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)

    job_id, accepted_topic = orchestrator.research_and_script_with_subject_retries(
        "How to Stay Calm When Your Boss Changes Priorities",
        {"ideas": [{"title": "You Do Not Need Everyone at Work to Like You"}]},
    )

    assert job_id == "job-accepted"
    assert accepted_topic == "How to Stay Calm When a Client Questions Your Work"
    assert [cmd[3:5] for cmd in commands] == [
        ["research", "How to Stay Calm When Your Boss Changes Priorities"],
        ["script", "job-rejected"],
        ["research", "How to Stay Calm When a Client Questions Your Work"],
        ["script", "job-accepted"],
    ]


def test_daily_orchestrator_keeps_valid_initial_whiskers_topic_outside_ledger_plan():
    orchestrator = load_daily_orchestrator()

    topic = orchestrator.enforce_ledger_topic(
        "When an Access Permission Blocks the File You Need",
        {"ideas": [{"title": "When the Dashboard Filter Is Wrong"}]},
    )

    assert topic == "When an Access Permission Blocks the File You Need"


def test_daily_orchestrator_matches_ledger_topic_with_channel_suffix():
    orchestrator = load_daily_orchestrator()

    topic = orchestrator.enforce_ledger_topic(
        "When the Version Label Is Stale | Stoic Modernized",
        {
            "ideas": [
                {"title": "When the Calendar Block Gets Broken"},
                {"title": "When the Version Label Is Stale"},
            ]
        },
    )

    assert topic == "When the Version Label Is Stale"


def test_daily_orchestrator_accepts_status_update_workplace_topic():
    orchestrator = load_daily_orchestrator()

    assert orchestrator.topic_quality_rejection_reason("When the Status Update Wants a Soft Exaggeration") is None


def test_daily_orchestrator_accepts_recent_operational_replacement_topics():
    orchestrator = load_daily_orchestrator()

    assert orchestrator.topic_quality_rejection_reason("When the Decision Record Is Incomplete") is None
    assert orchestrator.topic_quality_rejection_reason("When the Expense Receipt Upload Times Out Again") is None
    assert orchestrator.topic_quality_rejection_reason("When the Staging Server Times Out During Deployment") is None
    assert orchestrator.topic_quality_rejection_reason("When the VPN Drops During the Compliance Upload") is None
    assert orchestrator.topic_quality_rejection_reason("When One More Small Request Breaks Your Focus") is None


def test_daily_orchestrator_rejects_research_validated_topic_already_rejected(monkeypatch, tmp_path):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "RUN_DIR", tmp_path)
    agent_dir = tmp_path / "agent-notes"
    agent_dir.mkdir()
    monkeypatch.setattr(orchestrator, "AGENT_DIR", agent_dir)

    asked_prompts: list[str] = []

    def fake_agent(profile, prompt, note_name, *, timeout=orchestrator.AGENT_TIMEOUT):
        asked_prompts.append(prompt)
        if "new Stoic Modernized video subject" in prompt:
            return "When the Calendar Block Gets Broken"
        return "PASS"

    def fake_run_cmd(args, *, timeout, env=None, check=True):
        stage = args[3]
        topic_or_job = args[4]
        if stage == "research" and topic_or_job == "When an Access Permission Blocks the File You Need":
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-access-1\n", stderr=None)
        if stage == "script" and topic_or_job == "job-access-1":
            return subprocess.CompletedProcess(
                args,
                1,
                stdout="Script Subject Validation Failed!\nReason: subject-umbrella balance guardrail\n",
                stderr=None,
            )
        if stage == "research" and topic_or_job == "When the Calendar Block Gets Broken":
            return subprocess.CompletedProcess(
                args,
                0,
                stdout="Job ID: job-calendar\nValidated topic: When an Access Permission Blocks the File You Need\n",
                stderr=None,
            )
        if stage == "research" and topic_or_job == "When the Status Update Wants a Soft Exaggeration":
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-status\n", stderr=None)
        if stage == "script" and topic_or_job == "job-status":
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(
        orchestrator,
        "choose_fallback_topic",
        lambda ledger_context, rejected_topics: "When the Status Update Wants a Soft Exaggeration",
    )

    job_id, accepted_topic = orchestrator.research_and_script_with_subject_retries(
        "When an Access Permission Blocks the File You Need",
        {"ideas": [{"title": "When the Calendar Block Gets Broken"}]},
        max_attempts=3,
    )

    assert job_id == "job-status"
    assert accepted_topic == "When the Status Update Wants a Soft Exaggeration"
    assert any("already rejected validated topic" in p for p in asked_prompts)


def test_daily_orchestrator_preflights_duplicate_topic_before_research(monkeypatch, tmp_path):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "RUN_DIR", tmp_path)
    agent_dir = tmp_path / "agent-notes"
    agent_dir.mkdir()
    monkeypatch.setattr(orchestrator, "AGENT_DIR", agent_dir)

    commands: list[list[str]] = []

    def fake_agent(profile, prompt, note_name, *, timeout=orchestrator.AGENT_TIMEOUT):
        return "PASS"

    def fake_run_cmd(args, *, timeout, env=None, check=True):
        commands.append(list(args))
        stage = args[3]
        topic_or_job = args[4]
        if stage == "research" and topic_or_job == "When Feedback Threatens Your Reputation":
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-safe\n", stderr=None)
        if stage == "research" and topic_or_job == "When Your Boss Changes Priorities Again":
            return subprocess.CompletedProcess(
                args,
                1,
                stdout="Research blocked by duplicate-topic guardrail\n",
                stderr=None,
            )
        if stage == "script" and topic_or_job == "job-safe":
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(
        orchestrator,
        "topic_guardrail_rejection_reason",
        lambda topic: "Research blocked by duplicate-topic guardrail" if "Boss" in topic else None,
        raising=False,
    )
    monkeypatch.setattr(
        orchestrator,
        "choose_fallback_topic",
        lambda ledger_context, rejected_topics: "When Feedback Threatens Your Reputation",
    )

    job_id, accepted_topic = orchestrator.research_and_script_with_subject_retries(
        "When Your Boss Changes Priorities Again",
        {"ideas": [{"title": "When Feedback Threatens Your Reputation"}]},
        max_attempts=2,
    )

    assert job_id == "job-safe"
    assert accepted_topic == "When Feedback Threatens Your Reputation"
    assert [cmd[3:5] for cmd in commands] == [
        ["research", "When Feedback Threatens Your Reputation"],
        ["script", "job-safe"],
    ]


def test_daily_orchestrator_default_safe_subject_retry_budget_is_increased():
    orchestrator = load_daily_orchestrator()

    assert orchestrator.SAFE_SUBJECT_MAX_ATTEMPTS >= 12


def test_daily_orchestrator_parses_research_rejected_topics_for_retry_blacklist():
    orchestrator = load_daily_orchestrator()

    output = """
    [ResearchStage] Topic rejected before research: You Do Not Need Everyone at Work to Like You
    [ResearchStage] Reason: duplicate-topic guardrail
    [ResearchStage] Topic rejected before research: Why Rushing Makes Work Pressure Worse
    [ResearchStage] Reason: duplicate-topic guardrail
    """

    assert orchestrator.rejected_topics_from_output(output) == [
        "You Do Not Need Everyone at Work to Like You",
        "Why Rushing Makes Work Pressure Worse",
    ]


def test_daily_orchestrator_recognizes_boss_pressure_guardrail_rejection():
    orchestrator = load_daily_orchestrator()

    output = (
        "Research blocked by boss-pressure subject guardrail: this topic repeats a recent boss/manager "
        "pressure scenario. Research a different workplace actor and trigger before continuing."
    )

    assert orchestrator.is_subject_rejection_output(output) is True


def test_daily_orchestrator_rejects_malformed_replacement_topic_before_research():
    orchestrator = load_daily_orchestrator()

    reason = orchestrator.topic_quality_rejection_reason(
        "How Stoicism Helps When Stoicism For Modern Workers Feels Heavy"
    )

    assert reason
    assert "repeated" in reason.lower() or "awkward" in reason.lower()


def test_daily_orchestrator_requires_clear_workplace_trigger_for_replacement_topic():
    orchestrator = load_daily_orchestrator()

    reason = orchestrator.topic_quality_rejection_reason("Calm Is a Skill, Not a Personality")

    assert reason
    assert "workplace" in reason.lower()


def test_daily_orchestrator_accepts_natural_workplace_replacement_topic():
    orchestrator = load_daily_orchestrator()

    reason = orchestrator.topic_quality_rejection_reason(
        "How to Stay Calm When a Coworker Questions You in a Meeting"
    )

    assert reason is None


def test_daily_orchestrator_falls_back_to_concrete_operational_lane_when_ledger_is_exhausted(monkeypatch):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "recent_topic_blocklist", lambda limit=80: ["When FOMO Steals Your Career Focus"])

    topic = orchestrator.choose_fallback_topic(
        {"ideas": [{"title": "When the Handoff Has No Owner"}]},
        ["When the Handoff Has No Owner"],
    )

    assert topic != "When FOMO Steals Your Career Focus"
    assert orchestrator.topic_quality_rejection_reason(topic) is None


def test_daily_orchestrator_fallback_includes_coworker_relations_lane(monkeypatch):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "recent_topic_blocklist", lambda limit=80: [])

    blocked = [title for lane in orchestrator.CURATED_OPERATIONAL_FALLBACK_TOPICS.values() for title in lane]
    topic = orchestrator.choose_fallback_topic({"ideas": []}, blocked[:-1])

    assert topic == blocked[-1]
    assert "coworker" in topic.lower() or "peer" in topic.lower()
    assert orchestrator.topic_quality_rejection_reason(topic) is None


def test_daily_orchestrator_replacement_prompt_lists_recently_blocked_topics(monkeypatch):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(
        orchestrator,
        "recent_topic_blocklist",
        lambda limit=80: ["When the Export Timestamp Is Stale", "When the Calendar Has No White Space"],
    )

    prompt = orchestrator.replacement_topic_prompt(
        rejected_topic="When the Handoff Has No Owner",
        rejection_output="duplicate-topic guardrail",
        ledger_context={"ideas": []},
        rejected_topics=["When the Handoff Has No Owner"],
    )

    assert "Recently used or failed topics to avoid" in prompt
    assert "When the Export Timestamp Is Stale" in prompt
    assert "When the Calendar Has No White Space" in prompt


def test_daily_orchestrator_topic_prompt_names_coworker_grievance_lane():
    orchestrator = load_daily_orchestrator()

    prompt = orchestrator.format_ledger_topic_prompt({"ideas": []})

    assert "coworker" in prompt.lower()
    assert "grievance" in prompt.lower()


def test_daily_orchestrator_topic_prompt_explains_underused_umbrellas_and_slate():
    orchestrator = load_daily_orchestrator()

    prompt = orchestrator.format_ledger_topic_prompt(
        {
            "ideas": [
                {
                    "title": "When the Dashboard Filter Is Wrong",
                    "subject_umbrella": "loss_of_control",
                    "operational_trigger": "dashboard filter",
                    "experiment_tag": "operational_variety_batch",
                    "why_now": "fresh operational lane",
                    "objective": "discovery",
                },
                {
                    "title": "When the Phone Wins the Morning",
                    "subject_umbrella": "attention_distraction",
                    "operational_trigger": "phone notification",
                    "experiment_tag": "operational_variety_batch",
                    "why_now": "underused attention lane",
                    "objective": "discovery",
                },
            ],
            "underused_subject_umbrellas": ["attention_distraction", "fatigue_boundaries"],
            "subject_umbrella_policy": "no more than 2 of last 5 from one umbrella",
        }
    )

    assert "underused subject umbrellas" in prompt.lower()
    assert "attention_distraction" in prompt
    assert "generate a private slate" in prompt.lower()
    assert "subject_umbrella=loss_of_control" in prompt
