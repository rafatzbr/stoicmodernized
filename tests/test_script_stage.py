"""Tests for script generation stage."""

import json
import unittest.mock
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.config import VideoMode
from src.models import Script
from src.stages.script import ScriptGenerationError, ScriptStage


class TestScriptStage:
    """Tests for current Stoic Modernized script helpers."""

    def test_load_ledger_context_prefers_latest_artifacts(self, tmp_path: Path) -> None:
        stage = ScriptStage(job_id="job-ledger-1", mock=False, video_mode=VideoMode.SHORT)
        stage.workspace_artifacts_dir = tmp_path
        stage.strategy_manager.artifacts_dir = tmp_path
        stage.strategy_manager.global_strategy_path = tmp_path / "state" / "ledger_strategy.json"
        stage.strategy_manager.global_strategy_path.parent.mkdir(parents=True, exist_ok=True)

        council = tmp_path / "stoic-modernized-council-plan-2026-05-10.md"
        analytics = tmp_path / "stoic-modernized-youtube-analytics-2026-05-10.md"
        metrics = tmp_path / "stoic-modernized-youtube-metrics-2026-05-09.md"
        council.write_text("# Plan\n- 4 discovery videos\n- 3 conversion videos\n", encoding="utf-8")
        analytics.write_text("# Analytics\n- Shorts feed dominates\n- Anxiety converts\n", encoding="utf-8")
        metrics.write_text("# Metrics\n- Concrete work framing wins\n", encoding="utf-8")

        result = stage._load_ledger_context()

        assert result["available"] is True
        assert str(council) in result["files"]
        assert "4 discovery videos" in result["summary"]
        assert "Shorts feed dominates" in result["summary"]
        assert result["global_strategy"]["distribution"]["primary_surface"] == "shorts_feed"

    def test_load_ledger_context_skips_global_fallback_when_job_packet_is_strong(self, tmp_path: Path) -> None:
        stage = ScriptStage(job_id="job-ledger-strong", mock=False, video_mode=VideoMode.SHORT)
        stage.workspace_artifacts_dir = tmp_path
        stage.strategy_manager.artifacts_dir = tmp_path
        stage.strategy_manager.global_strategy_path = tmp_path / "state" / "ledger_strategy.json"
        stage.strategy_manager.global_strategy_path.parent.mkdir(parents=True, exist_ok=True)

        council = tmp_path / "stoic-modernized-council-plan-2026-05-10.md"
        council.write_text("# Plan\n- global fallback that should not be used\n", encoding="utf-8")

        strategy_dir = stage.strategy_manager.project_root / "output" / "jobs" / stage.job_id / "strategy"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        (strategy_dir / "ledger_packet.json").write_text(
            json.dumps({"objective": "conversion", "packaging_angle": "identity-level anxiety", "script_goal": "convert workplace anxiety viewers"}),
            encoding="utf-8",
        )

        result = stage._load_ledger_context()

        assert result["job_packet"]["objective"] == "conversion"
        assert result["global_strategy"] == {}
        assert result["files"] == []
        assert "Per-job steering packet is present" in result["summary"]

    def test_build_scratch_prompt_includes_ledger_strategy(self) -> None:
        stage = ScriptStage(job_id="job-ledger-2", mock=False, video_mode=VideoMode.SHORT)
        prompt = stage._build_scratch_prompt(
            research_packet={"topic": "work anxiety"},
            whiskers_brief={"viewer_problem": "spiraling before meetings"},
            ledger_strategy={"audience_job": "conversion", "packaging_angle": "identity-level anxiety"},
        )

        assert "Ledger strategy:" in prompt
        assert "identity-level anxiety" in prompt
        assert "conversion" in prompt

    @pytest.mark.asyncio
    async def test_call_local_llm_strips_fences(self) -> None:
        stage = ScriptStage(job_id="job-1", mock=False, video_mode=VideoMode.SHORT)

        mock_resp = unittest.mock.MagicMock()
        mock_resp.raise_for_status = unittest.mock.MagicMock()
        mock_resp.json = unittest.mock.MagicMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": "```json\n{\"title\":\"Specific Title\",\"hook\":\"Specific hook\",\"narration\":\"Narration\",\"chapters\":[{\"title\":\"Hook\",\"timestamp\":0}],\"cta\":\"Specific cta\"}\n```"
                        }
                    }
                ]
            }
        )
        mock_client = unittest.mock.MagicMock()
        mock_client.__aenter__ = unittest.mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = unittest.mock.AsyncMock(return_value=None)
        mock_client.post = unittest.mock.AsyncMock(return_value=mock_resp)

        with unittest.mock.patch("httpx.AsyncClient", return_value=mock_client):
            parsed = await stage._call_local_llm("system", "user", 200)

        assert parsed["title"] == "Specific Title"
        assert parsed["chapters"][0]["title"] == "Hook"

    @pytest.mark.asyncio
    async def test_call_local_llm_salvages_partial_json(self) -> None:
        stage = ScriptStage(job_id="job-2", mock=False, video_mode=VideoMode.SHORT)

        broken = '{"title":"Specific Title","hook":"Specific hook","narration":"Narration text","chapters":[{"title":"Hook","timestamp":0}],"cta":"Specific cta"'
        mock_resp = unittest.mock.MagicMock()
        mock_resp.raise_for_status = unittest.mock.MagicMock()
        mock_resp.json = unittest.mock.MagicMock(return_value={"choices": [{"message": {"content": broken}}]})
        mock_client = unittest.mock.MagicMock()
        mock_client.__aenter__ = unittest.mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = unittest.mock.AsyncMock(return_value=None)
        mock_client.post = unittest.mock.AsyncMock(return_value=mock_resp)

        with unittest.mock.patch("httpx.AsyncClient", return_value=mock_client):
            parsed = await stage._call_local_llm("system", "user", 200)

        assert parsed["title"] == "Specific Title"
        assert parsed["cta"] == "Specific cta"

    def test_normalize_council_script_payload_builds_timed_short_narration(self) -> None:
        stage = ScriptStage(job_id="job-3", mock=False, video_mode=VideoMode.SHORT)
        payload = {
            "title": "Handling Micromanagement Without Losing Your Mind: A Stoic Perspective",
            "hook": "Micromanagement becomes unbearable when you let it colonize your attention.",
            "narration": "Micromanagement feels personal fast and it spreads through the whole day.\n\nControl your judgment, not your manager's mood, and protect your focus under pressure.\n\nAnswer with clarity, document decisions, and keep your composure when the notes keep coming.",
            "cta": "Follow for more practical Stoicism that actually helps you at work",
            "chapters": [{"title": "x", "timestamp": 1}],
        }

        normalized = stage._normalize_council_script_payload(payload)

        assert normalized["chapters"][0]["title"] == "Hook"
        assert "[0:00-0:12] Hook" in normalized["narration"]
        assert "[0:50-0:58] CTA" in normalized["narration"]
        assert "@stoic-modernized" in normalized["narration"]

    def test_parse_script_response_trims_short_title_and_keeps_cta_handle(self) -> None:
        stage = ScriptStage(job_id="job-4", mock=False, video_mode=VideoMode.SHORT)
        script = stage._parse_script_response(
            {
                "title": "How to Stop Overthinking Work Problems: A Stoic Perspective",
                "hook": "You keep replaying the meeting after it ended.",
                "narration": "You keep replaying the meeting after it ended and your body acts like the conversation is still happening.\n\nName what is in your control before you react, slow the story you are telling yourself, and return to the next useful action.\n\nUse that pause on the next message you send so you answer with clarity instead of feeding the spiral for the rest of the day.",
                "chapters": [],
                "cta": "Follow for practical Stoic tools at work.",
            },
            topic="overthinking work problems",
        )

        assert ":" not in script.title
        assert 4 <= len(script.title.split()) <= 9
        assert "@stoic-modernized" in script.cta

    def test_parse_script_response_does_not_prepend_hook_to_timed_short_script(self) -> None:
        stage = ScriptStage(job_id="job-4b", mock=False, video_mode=VideoMode.SHORT)
        script = stage._parse_script_response(
            {
                "title": "Stop Replaying Bad Meetings",
                "hook": "You keep replaying the meeting after it ended.",
                "narration": "[0:00-0:12] Hook\nYou keep replaying the meeting after it ended and your body still thinks it is happening.\n\n[0:12-0:30] Stoic Principle\nSeparate the event from the story you add to it so you stop feeding the spiral.\n\n[0:30-0:50] Workplace Application\nBefore your next reply, name what is in your control and answer the actual problem in front of you.\n\n[0:50-0:58] CTA\nSubscribe to @stoic-modernized for practical Stoic tools you can use at work.",
                "chapters": [],
                "cta": "Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            },
            topic="bad meetings",
        )

        assert script.narration.count("[0:00-0:12] Hook") == 1
        assert not script.narration.startswith("You keep replaying the meeting after it ended.\n\n[0:00-0:12] Hook")

    @pytest.mark.asyncio
    async def test_real_script_passes_whiskers_handoff_to_workflow(self) -> None:
        stage = ScriptStage(job_id="job-whiskers-1", mock=False, video_mode=VideoMode.SHORT)
        captured = {}

        async def fake_workflow(**kwargs):
            captured.update(kwargs)
            return Script(
                title="Handled Well Here",
                hook="Hook long enough",
                narration="Narration long enough to validate with you in the text and enough words to pass the gate.",
                chapters=[],
                cta="Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
                short_version="Short",
                generated_at=datetime.now(UTC),
            )

        stage._run_council_workflow = fake_workflow  # type: ignore[method-assign]

        await stage._real_script(
            {
                "topic": "work anxiety",
                "title": "Work Anxiety",
                "ledger_packet": {"objective": "conversion"},
                "whiskers_handoff": {"viewer_problem": "spiraling before meetings"},
            }
        )

        assert captured["ledger_packet"]["objective"] == "conversion"
        assert captured["whiskers_handoff"]["viewer_problem"] == "spiraling before meetings"

    @pytest.mark.asyncio
    async def test_real_script_retries_after_blocked_topic_drift(self) -> None:
        stage = ScriptStage(job_id="job-retry-1", mock=False, video_mode=VideoMode.SHORT)
        attempts: list[dict[str, object]] = []

        async def fake_workflow(**kwargs):
            attempts.append(kwargs)
            if len(attempts) == 1:
                raise ScriptGenerationError(
                    "Generated script rejected: script introduced blocked topic drift (slack) that was not present in the approved research topic 'strategic patience'."
                )
            return Script(
                title="Strategic Patience Wins",
                hook="You keep forcing decisions before the facts are ready.",
                narration="You keep forcing decisions before the facts are ready and that pressure makes weak choices look urgent. Separate urgency from importance, hold your pace, and finish the next useful step before you react. Use that pause the next time a thread starts pushing you into speed for its own sake. Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
                chapters=[],
                cta="Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
                short_version="Short",
                generated_at=datetime.now(UTC),
            )

        stage._run_council_workflow = fake_workflow  # type: ignore[method-assign]

        result = await stage._real_script(
            {
                "topic": "strategic patience",
                "title": "Strategic Patience",
                "ledger_packet": {"objective": "conversion"},
            }
        )

        assert result.title == "Strategic Patience Wins"
        assert len(attempts) == 2
        assert attempts[0]["retry_feedback"] is None
        assert "slack" in str(attempts[1]["retry_feedback"]).lower()

    def test_save_script_persists_steering_chain(self, tmp_path: Path) -> None:
        stage = ScriptStage(job_id="job-steering-save", mock=False, video_mode=VideoMode.SHORT)
        stage.script_dir = tmp_path / "script"
        stage.script_dir.mkdir(parents=True, exist_ok=True)
        stage.last_steering_chain = {
            "ledger_packet": {"objective": "conversion"},
            "whiskers_handoff": {"viewer_problem": "spiraling before meetings"},
            "whiskers_brief": {"topic_angle": "identity-level anxiety"},
            "ledger_strategy": {"packaging_angle": "identity first"},
        }

        path = stage.save_script(
            Script(
                title="Handled Well Here",
                hook="Hook long enough",
                narration="Narration long enough to be valid for persistence and includes you so it stays audience-directed.",
                chapters=[],
                cta="Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
                short_version="Short",
                generated_at=datetime.now(UTC),
            )
        )

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["steering_chain"]["ledger_packet"]["objective"] == "conversion"
        assert payload["whiskers_handoff"]["viewer_problem"] == "spiraling before meetings"
        assert payload["ledger_strategy"]["packaging_angle"] == "identity first"

    def test_short_cta_section_can_be_brief(self) -> None:
        stage = ScriptStage(job_id="job-6", mock=False, video_mode=VideoMode.SHORT)
        normalized = stage._normalize_council_script_payload(
            {
                "title": "Toxic Workplace Survival",
                "hook": "A toxic office can drain you faster than the workload itself.",
                "narration": "A toxic office can drain you faster than the workload itself if you keep reacting to every jab as if it deserves your whole nervous system.\n\nStoicism starts by separating what belongs to your judgment from what belongs to the chaos around you so your mind stops volunteering for extra damage.\n\nDocument what matters, reduce unnecessary exposure, and make your next calm move based on strategy instead of proving a point.",
                "cta": "Protect your energy.",
                "chapters": [],
            }
        )

        assert "Protect your energy." in normalized["narration"]
        assert "@stoic-modernized" in normalized["narration"]

    def test_short_quality_uses_spoken_words_not_timing_labels(self) -> None:
        stage = ScriptStage(job_id="job-7", mock=False, video_mode=VideoMode.SHORT)
        script = Script(
            title="Stop Replaying Bad Meetings",
            hook="You keep replaying the meeting after it ended.",
            narration="[0:00-0:12] Hook\nYou keep replaying the meeting after it ended and your body still thinks it is happening.\n\n[0:12-0:30] Stoic Principle\nSeparate the event from the story you add to it so you stop feeding the spiral and get your judgment back.\n\n[0:30-0:50] Workplace Application\nBefore your next reply, name what is in your control, slow down, and answer the actual problem in front of you instead of the one in your head.\n\n[0:50-0:58] CTA\nSubscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            chapters=[],
            cta="Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            short_version="short",
            generated_at=datetime.now(UTC),
        )

        stage._enforce_generated_script_quality(script)

    def test_parse_script_response_rejects_blocked_topic_drift_not_in_research_topic(self) -> None:
        stage = ScriptStage(job_id="job-8", mock=False, video_mode=VideoMode.SHORT)

        with pytest.raises(ScriptGenerationError, match="blocked topic drift"):
            stage._parse_script_response(
                {
                    "title": "Stop the Slack Loop",
                    "hook": "You keep checking Slack even when nothing important changed.",
                    "narration": "[0:00-0:12] Hook\nYou keep checking Slack even when nothing important changed, and your attention keeps splintering every time the window lights up.\n\n[0:12-0:30] Stoic Principle\nSeparate the event from the urge so you stop rehearsing every ping in your head and let the notification decide what kind of mind you bring to work.\n\n[0:30-0:50] Workplace Application\nBefore your next reply, pause, name what matters, finish the task already in front of you, and answer only the part that truly needs a response right now.\n\n[0:50-0:58] CTA\nSubscribe to @stoic-modernized for practical Stoic tools you can use at work.",
                    "chapters": [],
                    "cta": "Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
                },
                topic="strategic patience",
            )

    def test_short_quality_rejects_third_repeated_your_boss_opener(self, tmp_path: Path) -> None:
        stage = ScriptStage(job_id="current-job", mock=False, video_mode=VideoMode.SHORT)
        stage.job_dir = tmp_path / "current-job"
        stage.script_dir = stage.job_dir / "script"
        stage.script_dir.mkdir(parents=True, exist_ok=True)
        for idx, hook in enumerate(
            [
                "Your boss changed priorities at 4 PM. You feel the rush to prove you can adapt.",
                "Your boss calls an emergency meeting. You start over-explaining before anyone asks.",
            ]
        ):
            recent_dir = tmp_path / f"recent-{idx}" / "script"
            recent_dir.mkdir(parents=True, exist_ok=True)
            (recent_dir / "script.json").write_text(
                json.dumps({"hook": hook, "narration": hook, "title": "Recent Script"}),
                encoding="utf-8",
            )

        script = Script(
            title="Stay Steady Under Priority Pressure",
            hook="Your boss shifts priorities again. You can answer without surrendering your pace.",
            narration="[0:00-0:12] Hook\nYour boss shifts priorities again. You can answer without surrendering your pace.\n\n[0:12-0:30] Stoic Principle\nSeparate the request from the panic around it, because the assignment is outside your control and your judgment is not.\n\n[0:30-0:50] Workplace Application\nBefore replying, write the tradeoff, name the next useful action, and ask which deadline should move instead of silently absorbing the chaos.\n\n[0:50-0:58] CTA\nSubscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            chapters=[],
            cta="Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            short_version="short",
            generated_at=datetime.now(UTC),
        )

        with pytest.raises(ScriptGenerationError, match="repeats recent opener pattern: your boss"):
            stage._enforce_generated_script_quality(script)

    def test_short_quality_rejects_script_too_similar_to_recent_video(self, tmp_path: Path) -> None:
        stage = ScriptStage(job_id="current-job", mock=False, video_mode=VideoMode.SHORT)
        stage.job_dir = tmp_path / "current-job"
        stage.script_dir = stage.job_dir / "script"
        stage.script_dir.mkdir(parents=True, exist_ok=True)
        recent_dir = tmp_path / "recent-similar" / "script"
        recent_dir.mkdir(parents=True, exist_ok=True)
        (recent_dir / "script.json").write_text(
            json.dumps(
                {
                    "title": "Stop Resenting Priority Shifts",
                    "hook": "A deadline moves late Friday and your whole body wants to argue.",
                    "narration": "Separate the request from the resentment, name the tradeoff, write the next useful action, ask which deadline should move, and keep your pace instead of silently absorbing the urgency.",
                }
            ),
            encoding="utf-8",
        )
        script = Script(
            title="Handle Late Priority Shifts",
            hook="A deadline moves late Friday and your first impulse is to argue.",
            narration="[0:00-0:12] Hook\nA deadline moves late Friday and your first impulse is to argue.\n\n[0:12-0:30] Stoic Principle\nSeparate the request from resentment so the urgency does not own your judgment or pace.\n\n[0:30-0:50] Workplace Application\nName the tradeoff, write the next useful action, ask which deadline should move, and stop silently absorbing urgency that was never yours.\n\n[0:50-0:58] CTA\nSubscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            chapters=[],
            cta="Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            short_version="short",
            generated_at=datetime.now(UTC),
        )

        with pytest.raises(ScriptGenerationError, match="too similar to recent script"):
            stage._enforce_generated_script_quality(script)

    def test_build_scratch_prompt_lists_recent_openings_to_avoid(self, tmp_path: Path) -> None:
        stage = ScriptStage(job_id="current-job", mock=False, video_mode=VideoMode.SHORT)
        stage.job_dir = tmp_path / "current-job"
        for idx, hook in enumerate(
            [
                "Your boss calls an emergency 9 AM meeting.",
                "Your boss changes priorities right before close.",
            ]
        ):
            recent_dir = tmp_path / f"recent-job-{idx}" / "script"
            recent_dir.mkdir(parents=True, exist_ok=True)
            (recent_dir / "script.json").write_text(
                json.dumps({"title": "Recent", "hook": hook, "narration": "same"}),
                encoding="utf-8",
            )

        prompt = stage._build_scratch_prompt(
            research_packet={"topic": "priority shifts"},
            whiskers_brief={"work_scenario": "late-day priority changes"},
            ledger_strategy={},
        )

        assert "Recent script openings to avoid" in prompt
        assert "Your boss calls an emergency 9 AM meeting" in prompt
        assert "Do not start with `Your boss`" in prompt
        assert "different actor and trigger" in prompt
