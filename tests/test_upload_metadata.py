import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

import src.main as main
from src.config import Channel
from src.models import UploadResult
from src.stages.upload import YouTubeUploader


def test_load_steering_context_from_script_artifact(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    script_dir = job_dir / "script"
    script_dir.mkdir(parents=True, exist_ok=True)
    (script_dir / "script.json").write_text(
        json.dumps(
            {
                "steering_chain": {
                    "ledger_packet": {"objective": "conversion"},
                    "whiskers_handoff": {"viewer_problem": "spiraling after meetings"},
                    "ledger_strategy": {"packaging_angle": "identity-level anxiety"},
                }
            }
        ),
        encoding="utf-8",
    )

    uploader = YouTubeUploader(mock=True)
    steering = uploader._load_steering_context(str(job_dir))

    assert steering["ledger_packet"]["objective"] == "conversion"
    assert steering["whiskers_handoff"]["viewer_problem"] == "spiraling after meetings"
    assert steering["ledger_strategy"]["packaging_angle"] == "identity-level anxiety"


def test_topic_umbrella_tokens_do_not_misclassify_calendar_or_printer_as_loss_of_control() -> None:
    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)

    calendar_tokens = uploader._topic_family_tokens("When the Calendar Has No White Space")
    printer_tokens = uploader._topic_family_tokens("When the Printer Jammed Mid-Print")

    assert "loss_of_control" not in uploader._topic_umbrellas(calendar_tokens)
    assert "fatigue_boundaries" in uploader._topic_umbrellas(calendar_tokens)
    assert "loss_of_control" not in uploader._topic_umbrellas(printer_tokens)
    assert "everyday_inconvenience" in uploader._topic_umbrellas(printer_tokens)


def test_generate_default_description_uses_steering_context() -> None:
    uploader = YouTubeUploader(mock=True)
    description = uploader._generate_default_description(
        title="Work Anxiety",
        chapters=[],
        steering_context={
            "ledger_packet": {"recommended_angle": "Tie work anxiety to one Stoic move"},
            "whiskers_handoff": {
                "viewer_problem": "you keep replaying the meeting after it ended",
                "stoic_move": "Name what is in your control before reacting",
            },
        },
    )

    assert "replaying the meeting" in description
    assert "Name what is in your control before reacting" in description
    assert "@stoic-modernized" in description
    assert "#stoicism" in description


def test_generate_tags_adds_subject_specific_tags() -> None:
    uploader = YouTubeUploader(mock=True)
    tags = uploader._generate_tags(
        "Why Catastrophic Thinking Keeps Running Your Work Life",
        "Catastrophic thinking at work turns anxiety into a spiral after every bad meeting.",
        {
            "ledger_packet": {"packaging_angle": "identity-level anxiety"},
            "whiskers_handoff": {"viewer_problem": "spiraling after meetings", "stoic_move": "focus on control"},
        },
    )

    lowered = [tag.lower() for tag in tags]
    assert "work anxiety" in lowered
    assert "catastrophic thinking" in lowered
    assert "stop spiraling" in lowered
    assert any(tag in lowered for tag in ["anxiety spiral", "catastrophizing", "anxious thoughts", "dichotomy of control"])


def test_generate_hashtags_uses_subject_specific_terms() -> None:
    uploader = YouTubeUploader(mock=True)
    hashtags = uploader._generate_hashtags(
        "Why Catastrophic Thinking Keeps Running Your Work Life",
        "Catastrophic thinking at work turns anxiety into a spiral after every bad meeting.",
        {
            "ledger_packet": {"packaging_angle": "identity-level anxiety"},
            "whiskers_handoff": {"viewer_problem": "spiraling after meetings", "stoic_move": "focus on control"},
        },
    )

    lowered = hashtags.lower()
    assert "#stoicism" in lowered
    assert "#stoicmodernized" in lowered
    assert len(re.findall(r"(?<!\w)#\w+", hashtags)) <= 5
    assert any(tag in lowered for tag in ["#workanxiety", "#catastrophicthinking", "#stopspiraling"])


def test_description_hashtags_are_hard_capped_for_templates_and_ai_outputs() -> None:
    uploader = YouTubeUploader(mock=True)
    over_tagged = (
        "One sentence. #stoicism #stoicmodernized #workanxiety "
        "#anxietywork #workplaceanxiety #anxietymanagement #extra\n\nResources:\nBook https://example.com"
    )

    capped = uploader._generate_description("Work Anxiety", [], template=over_tagged)
    hashtags = re.findall(r"(?<!\w)#\w+", capped)

    assert len(hashtags) == 5
    assert "#anxietymanagement" not in capped
    assert "#extra" not in capped
    assert "Resources:" in capped


def test_default_description_hashtags_are_hard_capped_to_five() -> None:
    uploader = YouTubeUploader(mock=True)
    description = uploader._generate_default_description(
        "Why Catastrophic Thinking Keeps Running Your Work Life",
        [],
        steering_context={
            "ledger_packet": {"packaging_angle": "identity-level anxiety"},
            "whiskers_handoff": {"viewer_problem": "spiraling after meetings", "stoic_move": "focus on control"},
        },
    )
    hashtags = re.findall(r"(?<!\w)#\w+", description)

    assert len(hashtags) <= 5


def test_subject_tags_do_not_overfit_single_meeting_or_panic_mentions() -> None:
    uploader = YouTubeUploader(mock=True)
    script_text = (
        "When work feels urgent, speed can look smart right before it makes the wrong call. "
        "Strategic patience starts by separating pressure from judgment. The deadline is real, but panic is optional. "
        "In the next tense meeting, do not force an answer just to relieve the room."
    )

    tags = uploader._generate_tags(
        "Slow Down Before You Decide",
        script_text,
        {},
    )
    hashtags = uploader._generate_hashtags(
        "Slow Down Before You Decide",
        script_text,
        {},
    )

    lowered = [tag.lower() for tag in tags]
    assert "strategic patience" in lowered
    assert "decision making at work" in lowered
    assert "pause before reacting" in lowered
    assert "bad meetings" not in lowered
    assert "meeting anxiety" not in lowered
    assert "panic at work" not in lowered
    assert "#badmeetings" not in hashtags.lower()
    assert "#meetinganxiety" not in hashtags.lower()
    assert "#panicatwork" not in hashtags.lower()


def test_add_affiliate_links_rotates_from_allowed_pool() -> None:
    uploader = YouTubeUploader(mock=True)
    description = uploader._add_affiliate_links("Short description", seed_hint="work anxiety")

    assert "Resources:" in description
    allowed = {
        "https://amzn.to/3Na3Yrw",
        "https://amzn.to/40km3Gj",
        "https://amzn.to/40VhlyR",
        "https://amzn.to/4nnSCxK",
        "https://amzn.to/4tw8sb8",
        "https://amzn.to/3PtCaQ1",
    }
    found = [url for url in allowed if url in description]
    assert len(found) == 3


def test_resolve_metadata_title_avoids_awkward_anxiety_suffix() -> None:
    uploader = YouTubeUploader(mock=True)
    title = uploader._resolve_metadata_title(
        "Why Catastrophic Thinking Keeps Running Your Work Life",
        [],
        script_text="Work anxiety keeps turning normal stress into catastrophic thinking.",
        steering_context={
            "ledger_packet": {"packaging_angle": "identity-level anxiety"},
            "whiskers_handoff": {"viewer_problem": "work anxiety keeps hijacking your attention"},
        },
    )

    assert title == "Why Anxiety Keeps Running Your Work Life"
    assert "and anxiety" not in title.lower()


def test_generate_metadata_persists_steering_context(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    script_dir = job_dir / "script"
    script_dir.mkdir(parents=True, exist_ok=True)
    (script_dir / "script.json").write_text(
        json.dumps(
            {
                "ledger_packet": {"objective": "conversion", "packaging_angle": "identity-level anxiety"},
                "whiskers_handoff": {"viewer_problem": "you keep replaying the meeting after it ended"},
            }
        ),
        encoding="utf-8",
    )

    uploader = YouTubeUploader(mock=True)
    metadata = uploader.generate_metadata(
        script_title="Stop Replaying The Meeting",
        chapters=[],
        script_text="You keep replaying the meeting after it ended and feeding the spiral.",
        job_dir=str(job_dir),
    )

    assert metadata["steering_context"]["ledger_packet"]["objective"] == "conversion"
    assert metadata["title"].endswith("| Stoic Modernized")


def test_recent_video_duplicate_guardrail_blocks_near_duplicate(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "That instant urge to reply to every Slack notification is costing you focus. "
                    "Use a five-minute delay before reacting."
                )
            }
        ),
        encoding="utf-8",
    )
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "Stop the Slack Loop at Work | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "Your phone pings with a Slack message and you start reacting instantly. "
                    "Put the phone down and stop letting the notification command you."
                )
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader._recent_video_duplicate_guardrail(
        {"title": "Stop the Slack Reaction Loop at Work | Stoic Modernized"},
        str(current_job),
    )

    assert error is not None
    assert "duplicate-content guardrail" in error


def test_topic_cooldown_guardrail_blocks_same_concept_family(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "Slack notifications train you to react before you think. "
                    "Turn off the pings and decide when messages deserve your attention."
                )
            }
        ),
        encoding="utf-8",
    )
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "Stop the Slack Loop at Work | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "Every Slack message feels urgent, so you keep checking the notification loop. "
                    "Break the habit by choosing when to look."
                )
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader._recent_video_duplicate_guardrail(
        {"title": "Stop Reacting To Slack Notifications Immediately | Stoic Modernized"},
        str(current_job),
    )

    assert error is not None
    assert "same-month subject guardrail" in error


def test_same_month_guardrail_allows_distinct_topic_with_only_soft_sentiment_overlap(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_job.mkdir(parents=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "Why Promotion Anxiety Gets Worse When You Rush | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps({"short_version": "Promotion anxiety makes you react to every review signal as a verdict."}),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_topic_for_research(
        "When Job Security Fear Takes Over the Morning",
        str(current_job),
    )

    assert error is None


def test_same_month_guardrail_blocks_same_coworker_grievance_but_allows_different_one(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_job.mkdir(parents=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "When a Coworker Takes Credit for Your Work | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps({"short_version": "A coworker takes credit for your work, and resentment wants to take over."}),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)

    same_grievance = uploader.validate_topic_for_research(
        "When a Coworker Takes Credit for the Work You Delivered",
        str(current_job),
    )
    different_grievance = uploader.validate_topic_for_research(
        "When a Coworker's Passive Aggressive Comment Follows You Home",
        str(current_job),
    )

    assert same_grievance is not None
    assert "guardrail" in same_grievance
    assert different_grievance is None


def test_topic_cooldown_uses_stable_artifact_date_not_metadata_edit_mtime(monkeypatch, tmp_path: Path) -> None:
    """Editing old metadata must not make upload stricter than early validation.

    The daily script validates before media spend. If a maintenance edit later touches
    an old metadata file, upload should not suddenly treat that old video as being in
    the rolling recent cooldown window.
    """
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "title": "Stop Meeting Anxiety Before 9 AM",
                "short_version": (
                    "Meeting anxiety creates pressure before the room even fills. "
                    "Name what you control and enter the meeting steady."
                ),
            }
        ),
        encoding="utf-8",
    )

    prior_job = jobs_dir / "old-edited-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps(
            {
                "title": "Failure Meditation Beats Reacting Under Pressure | Stoic Modernized",
                "steering_context": {
                    "ledger_packet": {"generated_at": "2026-05-18T13:01:07+00:00"}
                },
            }
        ),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "Imagine your biggest project collapses tomorrow and the pressure creates anxiety. "
                    "Prepare calmly before reacting."
                )
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_script_for_generation(
        metadata={"title": "Stop Meeting Anxiety Before 9 AM | Stoic Modernized"},
        job_dir=str(current_job),
    )

    assert error is None



def test_topic_cooldown_uses_script_date_when_metadata_lacks_date(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "title": "Stop Meeting Anxiety Before 9 AM",
                "short_version": "Meeting pressure and anxiety can distort your first judgment.",
            }
        ),
        encoding="utf-8",
    )

    prior_job = jobs_dir / "old-script-date-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "Slow Down Before You Decide | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-05-17T20:24:00Z",
                "short_version": "A meeting deadline can create pressure, but panic is optional.",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_script_for_generation(
        metadata={"title": "Stop Meeting Anxiety Before 9 AM | Stoic Modernized"},
        job_dir=str(current_job),
    )

    assert error is None



def test_recent_video_duplicate_guardrail_allows_different_angle(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": "Stop replaying bad meetings by naming the one fact you actually control."
            }
        ),
        encoding="utf-8",
    )
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "Stop the Slack Loop at Work | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": "Your phone pings with a Slack message and you start reacting instantly."
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader._recent_video_duplicate_guardrail(
        {"title": "How to Stop Replaying a Bad Meeting | Stoic Modernized"},
        str(current_job),
    )

    assert error is None


def test_same_month_subject_guardrail_blocks_monthly_repeat(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "Deadline anxiety makes every work deadline feel like a threat. "
                    "The Stoic move is to separate the due date from the panic spiral."
                )
            }
        ),
        encoding="utf-8",
    )
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "How To Stay Calm When Work Deadlines Are Uncontrollable | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "An uncontrollable deadline can trigger anxiety before the work even starts. "
                    "Focus on the next useful action instead of trying to control the date."
                )
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader._recent_video_duplicate_guardrail(
        {"title": "Why Deadline Anxiety Runs Your Work Life | Stoic Modernized"},
        str(current_job),
    )

    assert error is not None
    assert "same-month subject guardrail" in error


def test_research_topic_validation_blocks_same_month_subject(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_job.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "How To Stay Calm When Work Deadlines Are Uncontrollable | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps({"short_version": "Deadlines create anxiety when you treat the due date as something you control."}),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_topic_for_research(
        "Why deadline anxiety runs your work life",
        str(current_job),
    )

    assert error is not None
    assert "same-month subject guardrail" in error


def test_research_topic_validation_blocks_expense_receipt_repeat_before_cats_spend(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_job.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-expense-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "When Finance Rejects Your Expense Report | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "Finance rejects your expense report over one missing receipt. "
                    "Open the report, attach the missing proof, and move the paperwork forward."
                ),
                "generated_at": "2026-06-04T16:41:59Z",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_topic_for_research(
        "When the Expense Receipt Goes Missing",
        str(current_job),
    )

    assert error is not None
    assert "same-month subject guardrail" in error
    assert "expense, receipt" in error


def test_script_subject_validation_blocks_expense_receipt_repeat_before_media(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "title": "Missing Receipt, Clean Ledger",
                "short_version": (
                    "The card charge is real. The receipt is gone. Accounting needs it today. "
                    "Open the card statement, write the vendor and amount, and send the clean note."
                ),
                "generated_at": "2026-06-05T16:53:55Z",
            }
        ),
        encoding="utf-8",
    )

    prior_job = jobs_dir / "prior-expense-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "When Finance Rejects Your Expense Report | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "Finance rejects your expense report over one missing receipt. "
                    "Ask one precise question and attach the missing proof."
                ),
                "generated_at": "2026-06-04T16:41:59Z",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_script_for_generation(
        metadata={"title": "Missing Receipt, Clean Ledger | Stoic Modernized"},
        job_dir=str(current_job),
    )

    assert error is not None
    assert "same-month subject guardrail" in error
    assert "expense, receipt" in error


def test_same_month_guardrail_ignores_only_generic_meeting_react_overlap(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "title": "Calendar Hold, Clean Focus",
                "short_version": (
                    "A calendar hold appears during your first focus block. The meeting may move, "
                    "but you do not need to react yet. Protect the next twenty minutes and write the one task you can finish."
                ),
                "generated_at": "2026-06-08T16:53:55Z",
            }
        ),
        encoding="utf-8",
    )

    prior_job = jobs_dir / "prior-criticism-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "Why Defending Makes Criticism Worse | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "A review meeting includes criticism and you want to react immediately. "
                    "Listen, separate fact from judgment, and answer only after the useful point is clear."
                ),
                "generated_at": "2026-06-03T16:41:59Z",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_script_for_generation(
        metadata={"title": "Calendar Hold, Clean Focus | Stoic Modernized"},
        job_dir=str(current_job),
    )

    assert error is None


def test_expense_receipt_guardrail_allows_unrelated_document_problem(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_job.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-expense-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "When Finance Rejects Your Expense Report | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps({"short_version": "Finance rejects your expense report over one missing receipt."}),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_topic_for_research(
        "When a Training Room Is Booked Twice",
        str(current_job),
    )

    assert error is None


def test_script_subject_validation_blocks_boss_pressure_repeat_from_recent_video(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "title": "Stop Reacting to Boss's Priority Shifts",
                "short_version": (
                    "Your boss shifts priorities at 4 PM on Friday. That panic you feel is a test of your focus. "
                    "Pause, name the tradeoff, and ask which deadline should move."
                ),
                "narration": (
                    "Your boss shifts priorities at 4 PM on Friday. That panic you feel is a test of your focus. "
                    "Pause, name the tradeoff, and ask which deadline should move."
                ),
                "chapters": [],
            }
        ),
        encoding="utf-8",
    )

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "Stop Resenting Last Minute Priority Shifts | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "Your boss just changed priorities at 4 PM on Friday. Stop resenting it and start being useful. "
                    "Treat your boss like a client, not an enemy, and ask which deadline should move."
                )
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_script_for_generation(
        metadata={"title": "Stop Reacting to Boss's Priority Shifts | Stoic Modernized"},
        job_dir=str(current_job),
    )

    assert error is not None
    assert "boss-pressure subject guardrail" in error


def test_research_topic_validation_blocks_boss_pressure_repeat_before_cats_spend(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_job.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "Stop Resenting Last Minute Priority Shifts | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "Your boss just changed priorities at 4 PM on Friday. Stop resenting it and start being useful."
                )
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_topic_for_research(
        "Your Boss's Priority Change Is a Test of Your Focus",
        str(current_job),
    )

    assert error is not None
    assert "boss-pressure subject guardrail" in error


def test_research_topic_validation_blocks_repeat_from_script_only_retry(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_job.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-script-only-job"
    prior_script_dir = prior_job / "script"
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "title": "Stop Reacting When Coworkers Steal Credit",
                "short_version": (
                    "Your coworker just took your idea in the meeting and claimed it as their own. "
                    "Do not react yet. That urge to correct them immediately is the trap."
                ),
                "generated_at": "2026-06-02T15:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_topic_for_research(
        "Your Coworker's Disrespect Only Wins If You React",
        str(current_job),
    )

    assert error is not None
    assert "same-month subject guardrail" in error
    assert "prior-script-only-job" in error


def test_script_subject_validation_blocks_repeat_from_script_only_retry(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "title": "Your Coworker's Disrespect Only Wins If You React",
                "short_version": (
                    "Your coworker just gave you a condescending greeting. Do not react. "
                    "Pause before the disrespect controls your day."
                ),
                "narration": "Your coworker disrespected you. Pause before you react.",
                "chapters": [],
            }
        ),
        encoding="utf-8",
    )

    prior_job = jobs_dir / "prior-script-only-job"
    prior_script_dir = prior_job / "script"
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "title": "Stop Reacting When Coworkers Steal Credit",
                "short_version": (
                    "Your coworker just took your idea in the meeting and claimed it as their own. "
                    "Do not react yet. That urge to correct them immediately is the trap."
                ),
                "generated_at": "2026-06-02T15:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_script_for_generation(
        metadata={"title": "Your Coworker's Disrespect Only Wins If You React | Stoic Modernized"},
        job_dir=str(current_job),
    )

    assert error is not None
    assert "same-month subject guardrail" in error
    assert "prior-script-only-job" in error


def test_script_subject_validation_blocks_before_expensive_generation(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "title": "Why Deadline Anxiety Runs Your Work Life",
                "short_version": "Deadline anxiety makes every work deadline feel like a threat.",
                "narration": "Deadline anxiety makes every work deadline feel like a threat.",
                "chapters": [],
            }
        ),
        encoding="utf-8",
    )

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "How To Stay Calm When Work Deadlines Are Uncontrollable | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps({"short_version": "An uncontrollable deadline can trigger anxiety before the work even starts."}),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_script_for_generation(
        metadata={"title": "Why Deadline Anxiety Runs Your Work Life | Stoic Modernized"},
        job_dir=str(current_job),
    )

    assert error is not None
    assert "same-month subject guardrail" in error


def test_scene_command_blocks_when_script_subject_validation_fails(monkeypatch, tmp_path: Path) -> None:
    script_path = tmp_path / "script.json"
    script_path.write_text(
        json.dumps(
            {
                "title": "Why Deadline Anxiety Runs Your Work Life",
                "short_version": "Deadline anxiety makes every work deadline feel like a threat.",
                "narration": "Deadline anxiety makes every work deadline feel like a threat.",
                "chapters": [],
            }
        ),
        encoding="utf-8",
    )
    job_record = SimpleNamespace(script_path=str(script_path))
    scene_run_called = False
    updates: list[tuple[tuple, dict]] = []

    def fail_validation(*args, **kwargs):
        raise typer.Exit(code=1)

    async def fake_scene_run(*args, **kwargs):
        nonlocal scene_run_called
        scene_run_called = True
        return None

    monkeypatch.setattr(main, "_load_job_record", lambda job_id: job_record)
    monkeypatch.setattr(main, "_resolve_video_mode", lambda job_id=None, explicit=None: main.VideoMode.SHORT)
    monkeypatch.setattr(main, "_resolve_channel", lambda channel, job_id=None: Channel.STOIC_MODERNIZED)
    monkeypatch.setattr(main, "_validate_script_subject_before_generation", fail_validation)
    monkeypatch.setattr(main.SceneStage, "run", fake_scene_run)
    monkeypatch.setattr(main.db, "update_job", lambda *args, **kwargs: updates.append((args, kwargs)))

    with pytest.raises(typer.Exit):
        main.scene(job_id="current-job", mock=True, channel=None)

    assert scene_run_called is False


def test_topic_cooldown_guardrail_allows_distinct_conflict_angle(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "Finance wants the cheapest option. Marketing wants the fastest one. "
                    "You do not need everyone to like you to do the job with dignity."
                )
            }
        ),
        encoding="utf-8",
    )
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "Your Coworkers Disrespect Only Wins If You React | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "A disrespectful coworker only wins if you react. "
                    "Pause before conflict turns into a personal spiral."
                )
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader._recent_video_duplicate_guardrail(
        {"title": "Why Seeking Approval Ruins Your Work Life | Stoic Modernized"},
        str(current_job),
    )

    assert error is None


def test_topic_cooldown_guardrail_ignores_single_trigger_plus_generic_overlap(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    current_script_dir = current_job / "script"
    current_script_dir.mkdir(parents=True, exist_ok=True)
    (current_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "Staying calm is a skill you practice with difficult coworkers. "
                    "Use the moment to state a boundary without turning the room into a fight."
                )
            }
        ),
        encoding="utf-8",
    )
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")

    prior_job = jobs_dir / "prior-job"
    prior_metadata_dir = prior_job / "metadata"
    prior_script_dir = prior_job / "script"
    prior_metadata_dir.mkdir(parents=True, exist_ok=True)
    prior_script_dir.mkdir(parents=True, exist_ok=True)
    (prior_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (prior_metadata_dir / "metadata.json").write_text(
        json.dumps({"title": "Your Coworkers Disrespect Only Wins If You React | Stoic Modernized"}),
        encoding="utf-8",
    )
    (prior_script_dir / "script.json").write_text(
        json.dumps(
            {
                "short_version": (
                    "A disrespectful coworker only wins if you react. "
                    "Pause before conflict turns into a personal spiral."
                )
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader._recent_video_duplicate_guardrail(
        {"title": "Calm Is Not A Trait It Is A Skill | Stoic Modernized"},
        str(current_job),
    )

    assert error is None


@pytest.mark.asyncio
async def test_upload_runs_duplicate_guardrail(monkeypatch, tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir(parents=True, exist_ok=True)
    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)

    monkeypatch.setattr(uploader, "_background_music_guardrail", lambda job_dir: None)
    monkeypatch.setattr(uploader, "_recent_video_duplicate_guardrail", lambda metadata, job_dir: "blocked")

    result = await uploader.upload(
        video_path="/tmp/video.mp4",
        metadata={"title": "Any Title | Stoic Modernized"},
        thumbnail_path=None,
        job_dir=str(job_dir),
    )

    assert result.upload_status == "blocked"
    assert result.error == "blocked"


def test_upload_regenerates_metadata_from_current_script(monkeypatch, tmp_path: Path) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    stale_metadata_path = tmp_path / "metadata.json"
    stale_metadata_path.write_text(json.dumps({"title": "Stop the Slack Loop at Work | Stoic Modernized"}), encoding="utf-8")

    job_record = SimpleNamespace(
        video_path=str(video_path),
        thumbnail_path=None,
        metadata_path=str(stale_metadata_path),
        script_path=str(tmp_path / "script.json"),
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(main, "_load_job_record", lambda job_id: job_record)
    monkeypatch.setattr(main, "_resolve_channel", lambda channel, job_id=None: Channel.STOIC_MODERNIZED)
    monkeypatch.setattr(
        main,
        "_generate_metadata_payload_for_job",
        lambda job_id, job_record, channel=None, mock=False: {
            "title": "Slow Down Before You Decide | Stoic Modernized",
            "description": "Clean description",
            "tags": ["stoicism"],
        },
    )
    monkeypatch.setattr(main, "_save_metadata", lambda job_id, payload: captured.setdefault("saved_metadata", payload))
    monkeypatch.setattr(main.db, "update_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_send_telegram_upload", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.settings, "youtube_api_key", "configured")

    async def fake_upload(self, video_path, metadata, thumbnail_path=None, job_dir=None):
        captured["video_path"] = video_path
        captured["metadata"] = metadata
        return UploadResult(video_id="abc123", video_url="https://www.youtube.com/watch?v=abc123", upload_status="completed")

    monkeypatch.setattr(YouTubeUploader, "upload", fake_upload)

    main.upload(job_id="job-123", mock=False, video_path=None, channel=None)

    assert captured["video_path"] == str(video_path)
    assert captured["saved_metadata"]["title"] == "Slow Down Before You Decide | Stoic Modernized"
    assert captured["metadata"]["title"] == "Slow Down Before You Decide | Stoic Modernized"


def _write_subject_job(jobs_dir: Path, job_name: str, title: str, script: str) -> Path:
    job = jobs_dir / job_name
    (job / "metadata").mkdir(parents=True, exist_ok=True)
    (job / "script").mkdir(parents=True, exist_ok=True)
    (job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (job / "metadata" / "metadata.json").write_text(json.dumps({"title": title}), encoding="utf-8")
    (job / "script" / "script.json").write_text(json.dumps({"short_version": script}), encoding="utf-8")
    return job


def test_umbrella_balance_blocks_overused_conflict_friction(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    (current_job / "script").mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (current_job / "script" / "script.json").write_text(
        json.dumps({"short_version": "Your boss turns the meeting into pressure. Pause before you react."}),
        encoding="utf-8",
    )
    _write_subject_job(
        jobs_dir,
        "prior-conflict-1",
        "Your Coworker Interrupts You Again | Stoic Modernized",
        "A coworker interrupts the meeting. You do not need to win the room.",
    )
    _write_subject_job(
        jobs_dir,
        "prior-conflict-2",
        "When Your Boss Rejects the Plan | Stoic Modernized",
        "Your boss rejects the plan and the pressure rises.",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_topic_for_research("Your Boss Changes the Meeting Again", str(current_job))

    assert error is not None
    assert "subject-umbrella balance guardrail" in error
    assert "conflict friction" in error


def test_umbrella_balance_allows_major_workplace_stressors_despite_hot_umbrella(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    (current_job / "script").mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (current_job / "script" / "script.json").write_text(
        json.dumps({"short_version": "Layoff rumors make job security feel fragile. Choose preparation over panic."}),
        encoding="utf-8",
    )
    _write_subject_job(
        jobs_dir,
        "prior-conflict-1",
        "Your Coworker Interrupts You Again | Stoic Modernized",
        "A coworker interrupts the meeting. You do not need to win the room.",
    )
    _write_subject_job(
        jobs_dir,
        "prior-conflict-2",
        "When Your Boss Rejects the Plan | Stoic Modernized",
        "Your boss rejects the plan and the pressure rises.",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)

    assert uploader.validate_topic_for_research("When Layoff Rumors Steal the Workday", str(current_job)) is None
    assert uploader.validate_topic_for_research("When FOMO Steals Your Career Focus", str(current_job)) is None
    assert uploader.validate_topic_for_research("When a Work Conflict Follows You Home", str(current_job)) is None


def test_umbrella_balance_allows_underused_attention_topic(monkeypatch, tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    current_job = jobs_dir / "current-job"
    (current_job / "script").mkdir(parents=True, exist_ok=True)
    (current_job / "job.json").write_text(json.dumps({"channel": Channel.STOIC_MODERNIZED.value}), encoding="utf-8")
    (current_job / "script" / "script.json").write_text(
        json.dumps({"short_version": "Your phone wins the morning when attention is left undefended."}),
        encoding="utf-8",
    )
    _write_subject_job(
        jobs_dir,
        "prior-conflict-1",
        "Your Coworker Interrupts You Again | Stoic Modernized",
        "A coworker interrupts the meeting. You do not need to win the room.",
    )
    _write_subject_job(
        jobs_dir,
        "prior-conflict-2",
        "When Your Boss Rejects the Plan | Stoic Modernized",
        "Your boss rejects the plan and the pressure rises.",
    )

    monkeypatch.setattr("src.stages.upload.settings.jobs_dir", jobs_dir)

    uploader = YouTubeUploader(mock=True, channel=Channel.STOIC_MODERNIZED)
    error = uploader.validate_topic_for_research("The Phone Wins the Morning", str(current_job))

    assert error is None
