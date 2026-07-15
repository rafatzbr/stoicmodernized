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


def test_daily_orchestrator_retries_transient_script_generation_failure(monkeypatch, tmp_path):
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
        if stage == "research":
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-transient\n", stderr=None)
        if stage == "script" and topic_or_job == "job-transient" and len([cmd for cmd in commands if cmd[3] == "script"]) == 1:
            return subprocess.CompletedProcess(
                args,
                1,
                stdout="[ScriptStage] LLM call failed: \n\nScript Generation Failed!\nReason: Script generation failed:\n",
                stderr=None,
            )
        if stage == "script" and topic_or_job == "job-transient":
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "local_llm_subject_slate", lambda context, rejected_topics: ["When the Noisy Workspace Pulls Your Attention"])

    job_id, accepted_topic = orchestrator.research_and_script_with_subject_retries(
        "When a Password Reset Blocks the Login You Need",
        {"ideas": [{"title": "When a Password Reset Blocks the Login You Need"}]},
    )

    assert job_id == "job-transient"
    assert accepted_topic == "When a Password Reset Blocks the Login You Need"
    assert [cmd[3:5] for cmd in commands] == [
        ["research", "When a Password Reset Blocks the Login You Need"],
        ["script", "job-transient"],
        ["script", "job-transient"],
    ]
    assert (agent_dir / "04-script-transient-retry-attempt-1-1.txt").exists()


def test_daily_orchestrator_uses_bounded_script_stage_timeout(monkeypatch, tmp_path):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "RUN_DIR", tmp_path)
    agent_dir = tmp_path / "agent-notes"
    agent_dir.mkdir()
    monkeypatch.setattr(orchestrator, "AGENT_DIR", agent_dir)
    monkeypatch.setattr(orchestrator, "SCRIPT_STAGE_TIMEOUT", 17)

    observed_timeouts: list[tuple[str, int]] = []

    def fake_agent(profile, prompt, note_name, *, timeout=orchestrator.AGENT_TIMEOUT):
        return "PASS"

    def fake_run_cmd(args, *, timeout, env=None, check=True):
        stage = args[3]
        observed_timeouts.append((stage, timeout))
        if stage == "research":
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-bounded\n", stderr=None)
        if stage == "script":
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)

    job_id, _ = orchestrator.research_and_script_with_subject_retries(
        "When a Password Reset Blocks the Login You Need",
        {"ideas": [{"title": "When a Password Reset Blocks the Login You Need"}]},
    )

    assert job_id == "job-bounded"
    assert observed_timeouts == [("research", orchestrator.STAGE_TIMEOUT), ("script", 17)]


def test_daily_orchestrator_recovers_script_timeout_with_deterministic_fallback(monkeypatch, tmp_path):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "RUN_DIR", tmp_path)
    agent_dir = tmp_path / "agent-notes"
    agent_dir.mkdir()
    monkeypatch.setattr(orchestrator, "AGENT_DIR", agent_dir)

    script_envs: list[dict | None] = []

    def fake_agent(profile, prompt, note_name, *, timeout=orchestrator.AGENT_TIMEOUT):
        return "PASS"

    def fake_run_cmd(args, *, timeout, env=None, check=True):
        stage = args[3]
        if stage == "research":
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-timeout\n", stderr=None)
        if stage == "script":
            script_envs.append(env)
            if len(script_envs) == 1:
                return subprocess.CompletedProcess(args, 124, stdout="[timeout 17s] script\n", stderr=None)
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)

    job_id, _ = orchestrator.research_and_script_with_subject_retries(
        "When a Password Reset Blocks the Login You Need",
        {"ideas": [{"title": "When a Password Reset Blocks the Login You Need"}]},
    )

    assert job_id == "job-timeout"
    assert script_envs[0] is None
    fallback_env = script_envs[1]
    assert fallback_env is not None
    assert fallback_env["STOIC_FORCE_DETERMINISTIC_SCRIPT"] == "true"
    assert (agent_dir / "04-script-timeout-attempt-1.txt").exists()


def test_daily_orchestrator_continues_when_timeout_fallback_hits_subject_guardrail(monkeypatch, tmp_path):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "RUN_DIR", tmp_path)
    agent_dir = tmp_path / "agent-notes"
    agent_dir.mkdir()
    monkeypatch.setattr(orchestrator, "AGENT_DIR", agent_dir)

    commands: list[list[str]] = []
    script_envs: list[dict | None] = []

    def fake_agent(profile, prompt, note_name, *, timeout=orchestrator.AGENT_TIMEOUT):
        return "PASS"

    def fake_run_cmd(args, *, timeout, env=None, check=True):
        commands.append(list(args))
        stage = args[3]
        topic_or_job = args[4]
        if stage == "research" and topic_or_job == "When a Coworker Takes Credit in the Meeting, Ask One Clean Question":
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-duplicate\n", stderr=None)
        if stage == "script" and topic_or_job == "job-duplicate":
            script_envs.append(env)
            if len(script_envs) == 1:
                return subprocess.CompletedProcess(args, 124, stdout="[timeout 240s] script\n", stderr=None)
            if len(script_envs) == 2:
                return subprocess.CompletedProcess(
                    args,
                    1,
                    stdout=(
                        "Script Subject Validation Failed!\n"
                        "Reason: Upload blocked by duplicate-content guardrail: this video is too similar\n"
                    ),
                    stderr=None,
                )
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        if stage == "research" and topic_or_job == "When the Printer Queue Stops the Morning":
            assert args[-2:] == ["--job-id", "job-duplicate"]
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-duplicate\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "local_llm_subject_slate", lambda context, rejected_topics: ["When the Noisy Workspace Pulls Your Attention"])

    job_id, accepted_topic = orchestrator.research_and_script_with_subject_retries(
        "When a Coworker Takes Credit in the Meeting, Ask One Clean Question",
        {"ideas": []},
        max_attempts=2,
    )

    assert job_id == "job-duplicate"
    assert accepted_topic == "When the Printer Queue Stops the Morning"
    assert [cmd[3:5] for cmd in commands] == [
        ["research", "When a Coworker Takes Credit in the Meeting, Ask One Clean Question"],
        ["script", "job-duplicate"],
        ["script", "job-duplicate"],
        ["research", "When the Printer Queue Stops the Morning"],
        ["script", "job-duplicate"],
    ]
    assert commands[3][-2:] == ["--job-id", "job-duplicate"]
    assert script_envs[1] is not None
    assert script_envs[1]["STOIC_FORCE_DETERMINISTIC_SCRIPT"] == "true"
    assert (agent_dir / "04-script-fallback-rejection-attempt-1.txt").exists()


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

    script_attempts = 0

    def fake_run_cmd(args, *, timeout, env=None, check=True):
        nonlocal script_attempts
        commands.append(list(args))
        stage = args[3]
        topic_or_job = args[4]
        if stage == "research":
            if topic_or_job != "How to Stay Calm When Your Boss Changes Priorities":
                assert args[-2:] == ["--job-id", "job-rejected"]
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-rejected\n", stderr=None)
        if stage == "script" and topic_or_job == "job-rejected":
            script_attempts += 1
            if script_attempts == 1:
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
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "local_llm_subject_slate", lambda context, rejected_topics: ["When the Noisy Workspace Pulls Your Attention"])

    job_id, accepted_topic = orchestrator.research_and_script_with_subject_retries(
        "How to Stay Calm When Your Boss Changes Priorities",
        {
            "ideas": [
                {"title": "How to Stay Calm When Your Boss Changes Priorities"},
                {"title": "Handle Interruptions Without Losing Your Place"},
            ]
        },
    )

    assert job_id == "job-rejected"
    assert accepted_topic == "When the Printer Queue Stops the Morning"
    assert any("same-month subject guardrail" in prompt for prompt in asked_prompts) is False
    assert [cmd[3:5] for cmd in commands] == [
        ["research", "How to Stay Calm When Your Boss Changes Priorities"],
        ["script", "job-rejected"],
        ["research", "When the Printer Queue Stops the Morning"],
        ["script", "job-rejected"],
    ]
    assert commands[2][-2:] == ["--job-id", "job-rejected"]
    assert (agent_dir / "04-deterministic-fallback-attempt-2.txt").exists()


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

    script_attempts = 0

    def fake_run_cmd(args, *, timeout, env=None, check=True):
        nonlocal script_attempts
        commands.append(list(args))
        stage = args[3]
        topic_or_job = args[4]
        if stage == "research":
            if topic_or_job != "How to Stay Calm When Your Boss Changes Priorities":
                assert args[-2:] == ["--job-id", "job-rejected"]
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-rejected\n", stderr=None)
        if stage == "script" and topic_or_job == "job-rejected":
            script_attempts += 1
            if script_attempts == 1:
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
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "local_llm_subject_slate", lambda context, rejected_topics: ["When the Noisy Workspace Pulls Your Attention"])

    job_id, accepted_topic = orchestrator.research_and_script_with_subject_retries(
        "How to Stay Calm When Your Boss Changes Priorities",
        {"ideas": [{"title": "You Do Not Need Everyone at Work to Like You"}]},
    )

    assert job_id == "job-rejected"
    assert accepted_topic == "When the Printer Queue Stops the Morning"
    assert [cmd[3:5] for cmd in commands] == [
        ["research", "How to Stay Calm When Your Boss Changes Priorities"],
        ["script", "job-rejected"],
        ["research", "When the Printer Queue Stops the Morning"],
        ["script", "job-rejected"],
    ]
    assert commands[2][-2:] == ["--job-id", "job-rejected"]


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

    script_attempts = 0

    def fake_run_cmd(args, *, timeout, env=None, check=True):
        nonlocal script_attempts
        stage = args[3]
        topic_or_job = args[4]
        if stage == "research" and topic_or_job == "When an Access Permission Blocks the File You Need":
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-access-1\n", stderr=None)
        if stage == "script" and topic_or_job == "job-access-1":
            script_attempts += 1
            if script_attempts == 1:
                return subprocess.CompletedProcess(
                    args,
                    1,
                    stdout="Script Subject Validation Failed!\nReason: subject-umbrella balance guardrail\n",
                    stderr=None,
                )
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        if stage == "research" and topic_or_job == "When the Calendar Block Gets Broken":
            assert args[-2:] == ["--job-id", "job-access-1"]
            return subprocess.CompletedProcess(
                args,
                0,
                stdout="Job ID: job-access-1\nValidated topic: When an Access Permission Blocks the File You Need\n",
                stderr=None,
            )
        if stage == "research" and topic_or_job == "When the Status Update Wants a Soft Exaggeration":
            assert args[-2:] == ["--job-id", "job-access-1"]
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-access-1\n", stderr=None)
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

    assert job_id == "job-access-1"
    assert accepted_topic == "When the Status Update Wants a Soft Exaggeration"
    assert not any("already rejected validated topic" in p for p in asked_prompts)
    assert (agent_dir / "04-deterministic-fallback-attempt-2.txt").exists()


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


def test_daily_orchestrator_recognizes_research_quality_guardrail_rejection():
    orchestrator = load_daily_orchestrator()

    output = (
        "[ResearchStage] Research result rejected: When a Coworker Takes Credit in the Meeting\n"
        "[ResearchStage] Reason: research quality guardrail: sources are generic Stoic/self-help "
        "material, not a concrete workplace mechanism. Research a specific operational trigger "
        "before scripting.\n"
        "Research stage failed: No research topic passed validation."
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
    monkeypatch.setattr(orchestrator, "local_llm_subject_slate", lambda context, rejected_topics: [])

    topic = orchestrator.choose_fallback_topic(
        {"ideas": [{"title": "When the Handoff Has No Owner"}]},
        ["When the Handoff Has No Owner"],
    )

    assert topic != "When FOMO Steals Your Career Focus"
    assert orchestrator.topic_quality_rejection_reason(topic) is None


def test_daily_orchestrator_fallback_pool_is_mechanism_led(monkeypatch):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "recent_topic_blocklist", lambda limit=80: [])
    monkeypatch.setattr(orchestrator, "local_llm_subject_slate", lambda context, rejected_topics: [])

    blocked = [topic for topic in orchestrator.fallback_titles_by_lane({}) if orchestrator.topic_is_preflight_safe(topic)]
    topic = orchestrator.choose_fallback_topic({"ideas": []}, blocked[:-1])

    assert topic == blocked[-1]
    assert orchestrator.topic_quality_rejection_reason(topic) is None
    assert orchestrator.topic_research_specificity_rejection_reason(topic) is None


def test_daily_orchestrator_hard_fallback_uses_research_specific_mechanism(monkeypatch):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "recent_topic_blocklist", lambda limit=80: [])
    monkeypatch.setattr(orchestrator, "local_llm_subject_slate", lambda context, rejected_topics: [])

    blocked = orchestrator.fallback_titles_by_lane({})
    topic = orchestrator.choose_fallback_topic({"ideas": []}, blocked)

    assert topic == "When Career FOMO Makes the Status Update Feel Like a Verdict"
    assert orchestrator.topic_quality_rejection_reason(topic) is None
    assert orchestrator.topic_research_specificity_rejection_reason(topic) is None
    assert orchestrator.topic_sourceability_rejection_reason(topic) is None


def test_daily_orchestrator_hard_fallback_does_not_reuse_rejected_topic(monkeypatch):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "recent_topic_blocklist", lambda limit=80: [])
    monkeypatch.setattr(orchestrator, "local_llm_subject_slate", lambda context, rejected_topics: [])

    blocked = [title for lane in orchestrator.CURATED_OPERATIONAL_FALLBACK_TOPICS.values() for title in lane]
    topic = orchestrator.choose_fallback_topic(
        {"ideas": []},
        blocked + ["When Career FOMO Makes the Status Update Feel Like a Verdict"],
    )

    assert topic != "When Career FOMO Makes the Status Update Feel Like a Verdict"


def test_daily_orchestrator_rejects_low_confidence_unattended_source_topics():
    orchestrator = load_daily_orchestrator()

    assert orchestrator.topic_sourceability_rejection_reason("When the Source Date Range Is Missing")
    assert orchestrator.topic_sourceability_rejection_reason("When the Printer Jam Blocks the Signed Form") is None
    assert orchestrator.topic_sourceability_rejection_reason("When the Dashboard Filter Hides the Real Number") is None
    assert orchestrator.topic_sourceability_rejection_reason("When Career FOMO Makes the Status Update Feel Like a Verdict") is None
    assert orchestrator.topic_sourceability_rejection_reason("When a Work Conflict Follows You Home") is None


def test_daily_orchestrator_parses_local_llm_subject_slate() -> None:
    orchestrator = load_daily_orchestrator()

    raw = '{"topics":["When Career FOMO Makes the Status Update Feel Like a Verdict", {"title":"When Layoff Rumors Make Every Message Feel Dangerous"}]}'

    topics = orchestrator.extract_topic_slate(raw)

    assert "When Career FOMO Makes the Status Update Feel Like a Verdict" in topics
    assert "When Layoff Rumors Make Every Message Feel Dangerous" in topics


def test_daily_orchestrator_prefers_local_llm_subject_slate_over_static_pool(monkeypatch):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "recent_topic_blocklist", lambda limit=80: [])
    monkeypatch.setattr(orchestrator, "local_llm_subject_slate", lambda context, rejected_topics: [])
    monkeypatch.setattr(
        orchestrator,
        "local_llm_subject_slate",
        lambda context, rejected_topics: ["When Career FOMO Makes the Status Update Feel Like a Verdict"],
    )

    topic = orchestrator.choose_fallback_topic({"ideas": []}, [])

    assert topic == "When Career FOMO Makes the Status Update Feel Like a Verdict"


def test_daily_orchestrator_uses_deterministic_fallback_after_research_quality_rejection(monkeypatch, tmp_path):
    orchestrator = load_daily_orchestrator()
    monkeypatch.setattr(orchestrator, "RUN_DIR", tmp_path)
    agent_dir = tmp_path / "agent-notes"
    agent_dir.mkdir()
    monkeypatch.setattr(orchestrator, "AGENT_DIR", agent_dir)

    commands: list[list[str]] = []
    agent_calls: list[str] = []

    def fake_agent(profile, prompt, note_name, *, timeout=orchestrator.AGENT_TIMEOUT):
        agent_calls.append(note_name)
        return "PASS"

    def fake_run_cmd(args, *, timeout, env=None, check=True):
        commands.append(list(args))
        stage = args[3]
        topic_or_job = args[4]
        if stage == "research" and topic_or_job == "When the Approval Queue Goes Silent":
            return subprocess.CompletedProcess(
                args,
                1,
                stdout=(
                    "[ResearchStage] Reason: research quality guardrail: sources are generic "
                    "Stoic/self-help material, not a concrete workplace mechanism."
                ),
                stderr=None,
            )
        if stage == "research" and topic_or_job == "When the Dashboard Filter Hides the Real Number":
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-dashboard\n", stderr=None)
        if stage == "script" and topic_or_job == "job-dashboard":
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "recent_topic_blocklist", lambda limit=80: [])
    monkeypatch.setattr(orchestrator, "local_llm_subject_slate", lambda context, rejected_topics: [])
    monkeypatch.setattr(
        orchestrator,
        "fallback_titles_by_lane",
        lambda context: ["When the Dashboard Filter Hides the Real Number"],
    )

    job_id, accepted_topic = orchestrator.research_and_script_with_subject_retries(
        "When the Approval Queue Goes Silent",
        {"ideas": []},
        max_attempts=3,
    )

    assert job_id == "job-dashboard"
    assert accepted_topic == "When the Dashboard Filter Hides the Real Number"
    assert "04-whiskers-subject-retry-1" not in agent_calls
    assert (agent_dir / "04-deterministic-fallback-attempt-2.txt").exists()


def test_daily_orchestrator_reuses_job_after_research_subject_rejection(monkeypatch, tmp_path):
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
        if stage == "research" and topic_or_job == "When the Approval Queue Goes Silent":
            return subprocess.CompletedProcess(
                args,
                1,
                stdout=(
                    "Job ID: job-one\n"
                    "[ResearchStage] Reason: research quality guardrail: sources are generic "
                    "Stoic/self-help material, not a concrete workplace mechanism."
                ),
                stderr=None,
            )
        if stage == "research" and topic_or_job == "When the Dashboard Filter Hides the Real Number":
            assert args[-2:] == ["--job-id", "job-one"]
            return subprocess.CompletedProcess(args, 0, stdout="Job ID: job-one\n", stderr=None)
        if stage == "script" and topic_or_job == "job-one":
            return subprocess.CompletedProcess(args, 0, stdout="Script Complete!\n", stderr=None)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(orchestrator, "agent", fake_agent)
    monkeypatch.setattr(orchestrator, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(orchestrator, "topic_guardrail_rejection_reason", lambda topic: None)
    monkeypatch.setattr(orchestrator, "recent_topic_blocklist", lambda limit=80: [])
    monkeypatch.setattr(orchestrator, "local_llm_subject_slate", lambda context, rejected_topics: [])
    monkeypatch.setattr(
        orchestrator,
        "fallback_titles_by_lane",
        lambda context: ["When the Dashboard Filter Hides the Real Number"],
    )

    job_id, accepted_topic = orchestrator.research_and_script_with_subject_retries(
        "When the Approval Queue Goes Silent",
        {"ideas": []},
        max_attempts=2,
    )

    assert job_id == "job-one"
    assert accepted_topic == "When the Dashboard Filter Hides the Real Number"
    assert [cmd[3:5] for cmd in commands] == [
        ["research", "When the Approval Queue Goes Silent"],
        ["research", "When the Dashboard Filter Hides the Real Number"],
        ["script", "job-one"],
    ]


def test_daily_orchestrator_rejects_generic_self_help_fallback_topics():
    orchestrator = load_daily_orchestrator()

    assert orchestrator.topic_research_specificity_rejection_reason("When the Weekend Message Pulls You Back In")
    assert orchestrator.topic_research_specificity_rejection_reason("When the Client Asks for One More Revision")
    assert orchestrator.topic_research_specificity_rejection_reason("When a Password Reset Blocks the Login You Need") is None


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


def test_daily_orchestrator_topic_prompt_includes_tiktok_stats_steering():
    orchestrator = load_daily_orchestrator()

    prompt = orchestrator.format_ledger_topic_prompt({"ideas": []})

    assert "TikTok stats steering" in prompt
    assert "specific workplace trigger -> internal spiral -> one calm action" in prompt
    assert "Fear Of Looking Like A Self Promoter" in prompt
    assert "Why Status Games Get Worse When You Rush" in prompt
    assert "short and scenario-first" in prompt
    assert "10:30-11:30 AM" in prompt


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


def test_daily_orchestrator_topic_prompt_includes_notion_pipeline_ideas():
    orchestrator = load_daily_orchestrator()

    prompt = orchestrator.format_ledger_topic_prompt(
        {
            "notion_ideas": [
                {
                    "title": "When Your Coworker Turns Feedback Into a Status Game",
                    "status": "Idea",
                    "platforms": ["YouTube", "Facebook"],
                    "notes": "User-provided pipeline idea",
                }
            ],
            "ideas": [],
        }
    )

    assert "Notion Content Pipeline candidates" in prompt
    assert "high-priority user-generated ideas" in prompt
    assert "When Your Coworker Turns Feedback Into a Status Game" in prompt


def test_daily_orchestrator_ledger_titles_prioritizes_notion_pipeline_ideas():
    orchestrator = load_daily_orchestrator()

    titles = orchestrator.ledger_titles(
        {
            "notion_ideas": [{"title": "Notion First"}],
            "ideas": [{"title": "Ledger Second"}],
        }
    )

    assert titles[:2] == ["Notion First", "Ledger Second"]
