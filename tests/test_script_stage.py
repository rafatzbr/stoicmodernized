"""Tests for script generation stage."""

from src.config import VideoMode
from src.stages.script import ScriptStage


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
            "title": "Handling Micromanagement Without Losing Your Mind",
            "hook": "Micromanagement becomes unbearable when you let it colonize your attention.",
            "cta": "Subscribe for more.",
            "short_version": "A short version.",
            "sections": [
                {"title": "Hook", "narration": "Micromanagement feels personal fast."},
                {"title": "Stoic Principle", "narration": "Control your judgment, not your manager's mood."},
                {"title": "Workplace Application", "narration": "Answer with clarity, document decisions, and keep your composure."},
                {"title": "CTA", "narration": "Follow for more practical Stoicism."},
            ],
        }

        script = stage._payload_to_script(
            payload=payload,
            topic="micromanagement",
            research_title="Micromanagement: A Stoic Perspective",
            key_insights=["You control your response."],
            workplace_applications=["Pause before replying."],
        )

        assert script.title == payload["title"]
        assert len(script.chapters) == 4
        assert "[0:00-0:12] Hook" in script.narration
        assert "[0:50-0:58] CTA" in script.narration
        assert "Micromanagement feels personal fast." in script.narration

    async def test_real_script_falls_back_to_topic_specific_copy_when_llm_empty(self) -> None:
        stage = ScriptStage(job_id="job-3", mock=False, video_mode=VideoMode.LONG)

        async def fake_generate_with_local_llm(**_: object) -> dict:
            return {}

        stage._generate_with_local_llm = fake_generate_with_local_llm  # type: ignore[method-assign]

        script = await stage._real_script(
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

        assert script.title == "How Stoics Handle Micromanagement"
        assert "micromanagement" in script.narration.lower()
        assert "Clarify expectations in writing after meetings." in script.narration
        assert script.hook
        assert script.cta
        assert len(script.chapters) == 8
