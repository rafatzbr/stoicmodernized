import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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
    assert any(tag in lowered for tag in ["#workanxiety", "#catastrophicthinking", "#stopspiraling"])


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
