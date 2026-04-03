"""Tests for script generation stage."""

import json
from pathlib import Path

import pytest

from src.config import VideoMode
from src.stages.script import ScriptGenerationError, ScriptStage


class TestScriptStage:
    """Tests for real script stage helpers."""

    def test_parse_llm_json_strips_thinking_and_fences(self) -> None:
        stage = ScriptStage(job_id="job-1", mock=False, video_mode=VideoMode.SHORT)

        parsed = stage._parse_llm_json(
            """<think>hidden reasoning</think>
```json
{"title":"Specific Title","hook":"Specific hook","cta":"Specific cta","short_version":"Short text","sections":[{"title":"Hook","narration":"Topic-specific narration."}]}
```"""
        )

        assert parsed["title"] == "Specific Title"
        assert parsed["sections"][0]["narration"] == "Topic-specific narration."

    def test_payload_to_script_builds_timed_short_narration(self) -> None:
        stage = ScriptStage(job_id="job-2", mock=False, video_mode=VideoMode.SHORT)
        payload = {
            "title": "Handling Micromanagement Without Losing Your Mind: A Stoic Perspective",
            "hook": "Micromanagement becomes unbearable when you let it colonize your attention.",
            "cta": "Subscribe for more.",
            "short_version": "A short version.",
            "sections": [
                {"title": "Hook", "narration": "Micromanagement feels personal fast and it spreads through the whole day."},
                {"title": "Stoic Principle", "narration": "Control your judgment, not your manager's mood, and protect your focus under pressure."},
                {"title": "Workplace Application", "narration": "Answer with clarity, document decisions, and keep your composure when the notes keep coming."},
                {"title": "CTA", "narration": "Follow for more practical Stoicism that actually helps you at work"},
            ],
        }

        script = stage._payload_to_script(
            payload=payload,
            topic="micromanagement",
            research_title="Micromanagement: A Stoic Perspective",
            key_insights=["You control your response."],
            workplace_applications=["Pause before replying."],
        )

        assert script.title == "Handling Micromanagement Without Losing Your Mind"
        assert len(script.chapters) == 4
        assert "[0:00-0:12] Hook" in script.narration
        assert "[0:50-0:58] CTA" in script.narration
        assert "Micromanagement feels personal fast" in script.narration
        assert script.cta == "Subscribe for more."

    def test_repair_generated_payload_normalizes_short_title_and_syncs_cta(self) -> None:
        stage = ScriptStage(job_id="job-6", mock=False, video_mode=VideoMode.SHORT)

        repaired, repairs = stage._repair_generated_payload(
            {
                "title": "How To Stop Overthinking Work Problems Using Stoic Control: A Stoic Perspective",
                "hook": "Hook text.",
                "cta": "A different CTA.",
                "short_version": "Short version.",
                "sections": [
                    {"title": "Hook", "narration": "Hook narration with enough words to pass validation cleanly."},
                    {"title": "Stoic Principle", "narration": "Principle narration with enough topic specific words to pass validation."},
                    {"title": "Workplace Application", "narration": "Application narration with enough concrete workplace guidance to pass validation."},
                    {"title": "CTA", "narration": "Follow for more practical Stoic tools at work"},
                ],
            }
        )

        assert repaired["title"] == "How to Stop Overthinking Work Problems with Stoic Control"
        assert repaired["cta"] == "Follow for more practical Stoic tools at work."
        assert repaired["sections"][-1]["narration"] == repaired["cta"]
        assert "normalized_title" in repairs

    @pytest.mark.asyncio
    async def test_real_script_raises_when_llm_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
        stage = ScriptStage(job_id="job-3", mock=False, video_mode=VideoMode.LONG)

        async def fake_generate_with_local_llm(**_: object) -> dict:
            return {"success": False, "raw_response": "", "parsed_payload": {}, "error": "local_llm_returned_empty_content"}

        stage._generate_with_local_llm = fake_generate_with_local_llm  # type: ignore[method-assign]

        with pytest.raises(ScriptGenerationError, match="local_llm_returned_empty_content"):
            await stage._real_script(
                {
                    "topic": "micromanagement",
                    "title": "How Stoics Handle Micromanagement",
                    "key_insights": [
                        "Micromanagement hurts most when you treat every correction as a verdict on your worth.",
                        "Stoicism separates your effort from another person's need for control.",
                    ],
                    "workplace_applications": [
                        "Clarify expectations in writing after meetings.",
                        "Use a short pause before answering nitpicky messages.",
                        "Treat recurring friction as practice for steadiness.",
                    ],
                }
            )

        report = json.loads((stage.script_dir / "script_generation_report.json").read_text(encoding="utf-8"))
        parsed = json.loads((stage.script_dir / "local_llm_parsed.json").read_text(encoding="utf-8"))
        final_payload = json.loads((stage.script_dir / "script_generation_final.json").read_text(encoding="utf-8"))

        assert report["script_generation_succeeded"] is False
        assert report["failure_reason"] == "local_llm_returned_empty_content"
        assert report["used_fallback"] is False
        assert parsed == {}
        assert final_payload == {}
        assert not (stage.script_dir / "script.json").exists()

    def test_validate_generated_payload_rejects_generic_known_template(self) -> None:
        stage = ScriptStage(job_id="job-4", mock=False, video_mode=VideoMode.LONG)
        payload = {
            "title": "Stress at Work",
            "hook": "What if I told you that 2000 years of wisdom could help you handle stress at work better?",
            "cta": "Subscribe for more.",
            "short_version": "Stress at work feels bad, but Stoicism helps you stay calm and do better every day.",
            "sections": [
                {"title": title, "narration": "Welcome to Stoic Modernized. Today we're exploring how ancient Stoic philosophy can transform the way you handle workplace stress in your modern work life."}
                for title in stage._section_blueprint()
            ],
        }

        assert stage._validate_generated_payload(payload, topic="workplace stress") == "local_llm_payload_too_generic"

    @pytest.mark.asyncio
    async def test_real_script_records_rejected_payload_reason_and_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
        stage = ScriptStage(job_id="job-5", mock=False, video_mode=VideoMode.SHORT)

        async def fake_generate_with_local_llm(**_: object) -> dict:
            parsed_payload = {
                "title": "Micromanagement",
                "hook": "Micromanagement is hard.",
                "cta": "Subscribe.",
                "short_version": "Micromanagement is hard but Stoicism helps.",
                "sections": [
                    {"title": title, "narration": "Too short."}
                    for title in stage._section_blueprint()
                ],
            }
            return {
                "success": True,
                "raw_response": json.dumps(parsed_payload),
                "parsed_payload": parsed_payload,
                "error": None,
            }

        stage._generate_with_local_llm = fake_generate_with_local_llm  # type: ignore[method-assign]

        with pytest.raises(ScriptGenerationError, match="local_llm_section_1_too_short"):
            await stage._real_script(
                {"topic": "micromanagement", "title": "How Stoics Handle Micromanagement"}
            )
        report = json.loads((stage.script_dir / "script_generation_report.json").read_text(encoding="utf-8"))

        assert report["local_llm_success"] is True
        assert report["script_generation_succeeded"] is False
        assert report["failure_reason"] == "local_llm_section_1_too_short"
        assert report["used_fallback"] is False
