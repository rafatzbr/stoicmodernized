"""Tests for script generation stage."""

import json
import unittest.mock
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from src.config import VideoMode
from src.models import Script
from src.stages.script import STOIC_CTA_VARIANTS, ScriptGenerationError, ScriptStage


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

        assert "Milo strategy:" in prompt
        assert "identity-level anxiety" in prompt
        assert "conversion" in prompt

    @pytest.mark.asyncio
    async def test_force_deterministic_script_env_bypasses_slow_council(self, monkeypatch) -> None:
        stage = ScriptStage(job_id="job-force-deterministic", mock=False, video_mode=VideoMode.SHORT)
        monkeypatch.setenv("STOIC_FORCE_DETERMINISTIC_SCRIPT", "true")

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("council workflow should be bypassed")

        monkeypatch.setattr(stage, "_run_council_workflow", fail_if_called)

        script = await stage.run(
            {
                "topic": "When the Spreadsheet Formula Changes the Total",
                "key_insights": ["formula changes can distort a trusted total"],
                "workplace_applications": ["trace the formula before assigning blame"],
            }
        )

        assert script.title == "When the Spreadsheet Formula Changes the Total"
        assert "trace the formula before assigning blame" in script.narration
        assert "Stoic Modernized." not in script.narration
        assert script.cta.startswith("Subscribe to @stoic-modernized")
        assert script.cta in STOIC_CTA_VARIANTS

    @pytest.mark.asyncio
    async def test_force_deterministic_script_sanitizes_source_fragments(self, monkeypatch) -> None:
        stage = ScriptStage(job_id="job-force-deterministic-sanitize", mock=False, video_mode=VideoMode.SHORT)
        monkeypatch.setenv("STOIC_FORCE_DETERMINISTIC_SCRIPT", "true")

        script = await stage.run(
            {
                "topic": "When the Spreadsheet Formula Changes the Total",
                "key_insights": [
                    "[microsoft-excel] user // score: 1",
                    "Search results for 'When the Spreadsheet Formula Changes the Total' emphasize practical emotional regulation",
                ],
                "workplace_applications": ["http://example.com generic source"],
            }
        )

        assert "score:" not in script.narration
        assert "http" not in script.narration
        assert "Search results" not in script.narration
        assert "this trigger is only one input, not the whole verdict" in script.narration
        assert "spreadsheet, queue, review, or deadline" not in script.narration

    @pytest.mark.asyncio
    async def test_force_deterministic_script_uses_noise_specific_fallback(self, monkeypatch) -> None:
        stage = ScriptStage(job_id="job-force-deterministic-noise", mock=False, video_mode=VideoMode.SHORT)
        monkeypatch.setenv("STOIC_FORCE_DETERMINISTIC_SCRIPT", "true")

        script = await stage.run(
            {
                "topic": "When the Noisy Workspace Breaks Your Focus",
                "key_insights": ["office noise fragments attention and raises stress"],
                "workplace_applications": ["write the next tiny task before reacting"],
            }
        )

        assert "noisy workspace" in script.hook.lower()
        assert "speech, alerts, movement" in script.narration
        assert "status, blame, or urgency" not in script.narration
        assert "write the next tiny task before reacting" in script.narration

    @pytest.mark.asyncio
    async def test_force_deterministic_script_uses_printer_specific_fallback(self, monkeypatch) -> None:
        stage = ScriptStage(job_id="job-force-deterministic-printer", mock=False, video_mode=VideoMode.SHORT)
        monkeypatch.setenv("STOIC_FORCE_DETERMINISTIC_SCRIPT", "true")

        script = await stage.run(
            {
                "topic": "When the Printer Queue Stops the Morning",
                "key_insights": ["printer queues are operational blockers, not personal verdicts"],
                "workplace_applications": ["check the queue and communicate the delay"],
            }
        )

        assert "printer queue" in script.hook.lower()
        assert "queue, a device, or a stuck job" in script.narration
        assert "status, blame, or urgency" not in script.narration

    @pytest.mark.asyncio
    async def test_force_deterministic_script_uses_fomo_specific_fallback(self, monkeypatch) -> None:
        stage = ScriptStage(job_id="job-force-deterministic-fomo", mock=False, video_mode=VideoMode.SHORT)
        monkeypatch.setenv("STOIC_FORCE_DETERMINISTIC_SCRIPT", "true")

        script = await stage.run(
            {
                "topic": "When FOMO Makes You Reply to Every Slack Ping",
                "key_insights": ["FOMO is tied to social comparison and attention capture"],
                "workplace_applications": ["finish the current task before checking the thread"],
            }
        )

        assert "fomo" in script.hook.lower()
        assert "comparison, urgency" in script.narration.lower()
        assert "fOMO, Makes, Reply" not in script.narration

    @pytest.mark.asyncio
    async def test_force_deterministic_script_filters_css_layout_source_junk(self, monkeypatch) -> None:
        stage = ScriptStage(job_id="job-force-deterministic-context-switch", mock=False, video_mode=VideoMode.SHORT)
        monkeypatch.setenv("STOIC_FORCE_DETERMINISTIC_SCRIPT", "true")

        script = await stage.run(
            {
                "topic": "When Context Switching Breaks Your Deep Work",
                "key_insights": ["Content between column boxes in a multicol layout breaks like pages in paged media"],
                "workplace_applications": ["create physical or time-based friction before work"],
            }
        )

        assert "context switching" in script.hook.lower()
        assert "column boxes" not in script.narration
        assert "multicol" not in script.narration.lower()
        assert "paged media" not in script.narration.lower()

    def test_generated_script_rejects_unrelated_sports_source_contamination(self) -> None:
        stage = ScriptStage(job_id="job-source-contamination", mock=False, video_mode=VideoMode.SHORT)
        payload = {
            "title": "Ask For One Fact",
            "hook": "When the reorg rumor hits team chat, ask for one fact first.",
            "narration": (
                "When the reorg rumor hits team chat, ask for one fact first. "
                "Then separate the visible event from the story your mind adds. "
                "Choose one owner for clarity and one next action. "
                "The useful reminder is simple: for Team Colombia in the 2026 World Baseball Classic WBC due to a shoulder injury. "
                "Calm is keeping your judgment clean while work tries to make the moment bigger. "
                "Do the clear next step, leave a clean record, and return attention to what you can steer."
            ),
            "chapters": [
                {"title": "Hook", "timestamp": 0},
                {"title": "Stoic Principle", "timestamp": 12},
                {"title": "Workplace Application", "timestamp": 30},
                {"title": "CTA", "timestamp": 50},
            ],
            "cta": "Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
        }

        with pytest.raises(ScriptGenerationError, match="source contamination"):
            stage._parse_script_response(payload, "When the Reorg Rumor Hits Team Chat, Ask for One Fact")

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

    @pytest.mark.asyncio
    async def test_call_local_llm_retries_empty_content_payload(self) -> None:
        stage = ScriptStage(job_id="job-empty-retry", mock=False, video_mode=VideoMode.SHORT)

        empty_resp = unittest.mock.MagicMock()
        empty_resp.raise_for_status = unittest.mock.MagicMock()
        empty_resp.json = unittest.mock.MagicMock(return_value={"choices": [{"message": {"content": ""}}]})

        good_resp = unittest.mock.MagicMock()
        good_resp.raise_for_status = unittest.mock.MagicMock()
        good_resp.json = unittest.mock.MagicMock(
            return_value={"choices": [{"message": {"content": '{"title":"Recovered","hook":"Hook","narration":"Narration","chapters":[],"cta":"CTA"}'}}]}
        )

        mock_client = unittest.mock.MagicMock()
        mock_client.__aenter__ = unittest.mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = unittest.mock.AsyncMock(return_value=None)
        mock_client.post = unittest.mock.AsyncMock(side_effect=[empty_resp, good_resp])

        with unittest.mock.patch("httpx.AsyncClient", return_value=mock_client), unittest.mock.patch("asyncio.sleep", new=unittest.mock.AsyncMock()):
            parsed = await stage._call_local_llm("system", "user", 200)

        assert parsed["title"] == "Recovered"
        assert mock_client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_call_local_llm_retries_http_transport_failure(self) -> None:
        stage = ScriptStage(job_id="job-timeout-retry", mock=False, video_mode=VideoMode.SHORT)

        good_resp = unittest.mock.MagicMock()
        good_resp.raise_for_status = unittest.mock.MagicMock()
        good_resp.json = unittest.mock.MagicMock(
            return_value={"choices": [{"message": {"content": '{"title":"Recovered","hook":"Hook","narration":"Narration","chapters":[],"cta":"CTA"}'}}]}
        )

        mock_client = unittest.mock.MagicMock()
        mock_client.__aenter__ = unittest.mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = unittest.mock.AsyncMock(return_value=None)
        mock_client.post = unittest.mock.AsyncMock(side_effect=[httpx.ReadTimeout(""), good_resp])

        with unittest.mock.patch("httpx.AsyncClient", return_value=mock_client), unittest.mock.patch("asyncio.sleep", new=unittest.mock.AsyncMock()):
            parsed = await stage._call_local_llm("system", "user", 200)

        assert parsed["title"] == "Recovered"
        assert mock_client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_call_local_llm_reads_reasoning_content_when_content_is_blank(self) -> None:
        stage = ScriptStage(job_id="job-reasoning-content", mock=False, video_mode=VideoMode.SHORT)

        mock_resp = unittest.mock.MagicMock()
        mock_resp.raise_for_status = unittest.mock.MagicMock()
        mock_resp.json = unittest.mock.MagicMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "reasoning_content": '{"title":"Reasoning Payload","hook":"Hook","narration":"Narration","chapters":[],"cta":"CTA"}',
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

        assert parsed["title"] == "Reasoning Payload"

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
        assert "Subscribe to Stoic Modernized" in normalized["narration"]
        assert "@stoic-modernized" not in normalized["narration"]

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

    def test_cta_rotates_by_job_id_instead_of_hardcoding_one_phrase(self) -> None:
        ctas = {
            ScriptStage(job_id=f"rotating-cta-{idx}", mock=False, video_mode=VideoMode.SHORT)._ensure_cta_handle("Follow for steady work strategies.")
            for idx in range(12)
        }

        assert len(ctas) >= 3
        assert all(cta.startswith("Subscribe to @stoic-modernized") for cta in ctas)
        assert all(cta in STOIC_CTA_VARIANTS for cta in ctas)

    def test_short_cta_with_existing_handle_uses_single_standard_subscribe_line(self) -> None:
        stage = ScriptStage(job_id="job-4-cta", mock=False, video_mode=VideoMode.SHORT)
        normalized = stage._normalize_council_script_payload(
            {
                "title": "Stop Defending When Criticized",
                "hook": "Client feedback hits your ego fast.",
                "narration": "[0:00-0:12] Hook\nClient feedback hits your ego fast.\n\n[0:12-0:30] Stoic Principle\nYou control your judgment, not their words.\n\n[0:30-0:50] Workplace Application\nPause before you type and answer the work, not your pride.\n\n[0:50-0:58] CTA\nBreathe first. Reply second. Subscribe for steady work strategies. Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
                "chapters": [],
                "cta": "Breathe first. Reply second. Subscribe for steady work strategies. Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            }
        )

        cta_block = normalized["narration"].split("[0:50-0:58] CTA", 1)[1]
        assert cta_block.strip().startswith("Breathe first. Reply second. Subscribe to Stoic Modernized")
        assert "@stoic-modernized" not in cta_block
        assert "at stoic modernized" not in cta_block.lower()
        assert cta_block.lower().count("subscribe") == 1

    def test_parse_script_response_keeps_handle_in_cta_but_not_spoken_narration(self) -> None:
        stage = ScriptStage(job_id="job-4-cta-spoken", mock=False, video_mode=VideoMode.SHORT)
        script = stage._parse_script_response(
            {
                "title": "Stop Replaying Bad Meetings",
                "hook": "You keep replaying the meeting after it ended.",
                "narration": "[0:00-0:12] Hook\nYou keep replaying the meeting after it ended, and your body acts like the conversation is still happening.\n\n[0:12-0:30] Stoic Principle\nSeparate the event from the story you add to it so the old meeting stops borrowing attention from the current task.\n\n[0:30-0:50] Workplace Application\nBefore your next reply, name what is in your control, answer the actual problem, and leave the imagined trial alone.\n\n[0:50-0:58] CTA\nSubscribe to @stoic-modernized for practical Stoic tools you can use at work.",
                "chapters": [],
                "cta": "Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            },
            topic="bad meetings",
        )

        assert script.cta.startswith("Subscribe to @stoic-modernized")
        assert script.cta in STOIC_CTA_VARIANTS
        assert "Subscribe to Stoic Modernized" in script.narration
        assert "@stoic-modernized" not in script.narration

    def test_short_cta_strips_comment_to_receive_resource_promise(self) -> None:
        stage = ScriptStage(job_id="job-4-cta-promise", mock=False, video_mode=VideoMode.SHORT)
        normalized = stage._normalize_council_script_payload(
            {
                "title": "Slow Down Promotion Panic",
                "hook": "A promotion opening can steal your focus fast.",
                "narration": "[0:00-0:12] Hook\nA promotion opening can steal your focus fast.\n\n[0:12-0:30] Stoic Principle\nControl the action in front of you, not the title you imagine.\n\n[0:30-0:50] Workplace Application\nPause for sixty seconds before you apply and name the next useful step.\n\n[0:50-0:58] CTA\nWant more steady focus? Comment 'Control' below and Ill send you the one-page checklist. Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
                "chapters": [],
                "cta": "Comment 'Control' below and Ill send you the one-page checklist. Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            }
        )

        cta_block = normalized["narration"].split("[0:50-0:58] CTA", 1)[1]
        assert "Comment 'Control'" not in cta_block
        assert "send you" not in cta_block
        assert cta_block.strip().startswith("Want more steady focus. Subscribe to Stoic Modernized")

    def test_short_quality_rejects_viewer_delivery_promise(self) -> None:
        stage = ScriptStage(job_id="job-4-cta-promise-reject", mock=False, video_mode=VideoMode.SHORT)
        script = Script(
            title="Slow Down Promotion Panic",
            hook="A promotion opening can steal your focus fast.",
            narration="[0:00-0:12] Hook\nA promotion opening can steal your focus fast.\n\n[0:12-0:30] Stoic Principle\nControl the action in front of you, not the title you imagine.\n\n[0:30-0:50] Workplace Application\nPause for sixty seconds before you apply and name the next useful step.\n\n[0:50-0:58] CTA\nComment 'Control' below and Ill send you the one-page checklist. Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            chapters=[],
            cta="Comment 'Control' below and Ill send you the one-page checklist. Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            short_version="short",
            generated_at=datetime.now(UTC),
        )

        with pytest.raises(ScriptGenerationError, match="promises to send"):
            stage._enforce_generated_script_quality(script)

    def test_short_quality_rejects_standalone_brand_sentence(self) -> None:
        stage = ScriptStage(job_id="job-4-brand-only-reject", mock=False, video_mode=VideoMode.SHORT)
        script = Script(
            title="When Numbers Change Fast",
            hook="The spreadsheet changes and your chest tightens.",
            narration=(
                "The spreadsheet changes and your chest tightens. Separate the event from the story before you answer. "
                "Write the smallest fact you can verify right now, then fix the next true line. "
                "Do the clear next step, leave a clean record, and let the noise pass without becoming your standard. "
                "Stoic Modernized. Subscribe to Stoic Modernized for practical Stoic tools you can use at work."
            ),
            chapters=[],
            cta="Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            short_version="short",
            generated_at=datetime.now(UTC),
        )

        with pytest.raises(ScriptGenerationError, match="standalone brand-name sentence"):
            stage._enforce_generated_script_quality(script)

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
        assert "Subscribe to Stoic Modernized" in normalized["narration"]
        assert "@stoic-modernized" not in normalized["narration"]

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

    def test_parse_script_response_allows_workplace_vocab_without_global_keyword_ban(self) -> None:
        stage = ScriptStage(job_id="job-8", mock=False, video_mode=VideoMode.SHORT)

        script = stage._parse_script_response(
            {
                "title": "Stop the Slack Loop",
                "hook": "You keep checking Slack even when nothing important changed.",
                "narration": "[0:00-0:12] Hook\nYou keep checking Slack even when nothing important changed, and your attention keeps splintering every time the window lights up.\n\n[0:12-0:30] Stoic Principle\nSeparate the event from the urge so you stop rehearsing every ping in your head and let the notification decide what kind of mind you bring to work.\n\n[0:30-0:50] Workplace Application\nBefore your next reply, pause, name what matters, finish the task already in front of you, and answer only the part that truly needs a response right now.\n\n[0:50-0:58] CTA\nSubscribe to @stoic-modernized for practical Stoic tools you can use at work.",
                "chapters": [],
                "cta": "Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            },
            topic="strategic patience",
        )

        assert "Slack" in script.title

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

    def test_short_quality_rejects_overused_chest_tightens_phrase(self, tmp_path: Path) -> None:
        stage = ScriptStage(job_id="current-job", mock=False, video_mode=VideoMode.SHORT)
        stage.job_dir = tmp_path / "current-job"
        stage.script_dir = stage.job_dir / "script"
        stage.script_dir.mkdir(parents=True, exist_ok=True)
        for idx in range(2):
            recent_dir = tmp_path / f"recent-chest-{idx}" / "script"
            recent_dir.mkdir(parents=True, exist_ok=True)
            (recent_dir / "script.json").write_text(
                json.dumps(
                    {
                        "title": "Recent Script",
                        "hook": "Your chest tightens when the email lands.",
                        "narration": "Your chest tightens when the email lands. Separate fact from story before replying.",
                    }
                ),
                encoding="utf-8",
            )

        script = Script(
            title="Check the Export Before Replying",
            hook="Your chest tightens when the report number looks wrong.",
            narration="[0:00-0:12] Hook\nYour chest tightens when the report number looks wrong, and you want to explain before you verify.\n\n[0:12-0:30] Stoic Principle\nSeparate the impression from the fact so the first feeling does not become your decision.\n\n[0:30-0:50] Workplace Application\nCheck the export time, the filter, and the source table. Then send one clean correction instead of a defensive story.\n\n[0:50-0:58] CTA\nSubscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            chapters=[],
            cta="Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            short_version="short",
            generated_at=datetime.now(UTC),
        )

        with pytest.raises(ScriptGenerationError, match="repeats overused body-reaction phrase: your chest tightens"):
            stage._enforce_generated_script_quality(script)

    def test_short_quality_rejects_repeated_recent_title(self, tmp_path: Path) -> None:
        stage = ScriptStage(job_id="current-job", mock=False, video_mode=VideoMode.SHORT)
        stage.job_dir = tmp_path / "current-job"
        stage.script_dir = stage.job_dir / "script"
        stage.script_dir.mkdir(parents=True, exist_ok=True)
        recent_dir = tmp_path / "recent-title" / "script"
        recent_dir.mkdir(parents=True, exist_ok=True)
        (recent_dir / "script.json").write_text(
            json.dumps({"title": "Why Rushing Makes Work Pressure Worse", "hook": "A report is due soon.", "narration": "A report is due soon. Pause and verify before sending."}),
            encoding="utf-8",
        )
        script = Script(
            title="Why Rushing Makes Work Pressure Worse",
            hook="The export timestamp is stale, and speed will make the error louder.",
            narration="[0:00-0:12] Hook\nThe export timestamp is stale, and speed will make the error louder.\n\n[0:12-0:30] Stoic Principle\nTreat urgency as an impression, not an order. You still control verification and the next sentence.\n\n[0:30-0:50] Workplace Application\nCheck the timestamp, filter, and source. Then send one correction with the evidence attached.\n\n[0:50-0:58] CTA\nSubscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            chapters=[],
            cta="Subscribe to @stoic-modernized for practical Stoic tools you can use at work.",
            short_version="short",
            generated_at=datetime.now(UTC),
        )

        with pytest.raises(ScriptGenerationError, match="repeats recent title exactly"):
            stage._enforce_generated_script_quality(script)
