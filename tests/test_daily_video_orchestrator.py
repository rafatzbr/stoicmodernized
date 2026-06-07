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


def test_daily_orchestrator_falls_back_to_concrete_operational_lane_when_ledger_is_exhausted():
    orchestrator = load_daily_orchestrator()

    topic = orchestrator.choose_fallback_topic(
        {"ideas": [{"title": "When the Handoff Has No Owner"}]},
        ["When the Handoff Has No Owner"],
    )

    assert topic == "When a Spreadsheet Cell Breaks Your Patience During Reconciliation"
    assert orchestrator.topic_quality_rejection_reason(topic) is None
