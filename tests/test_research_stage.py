from pathlib import Path

import pytest

from src.stages.research import ResearchStage


def test_infer_source_detects_expected_source_types() -> None:
    stage = ResearchStage(job_id="test", mock=False)

    assert stage._infer_source("https://en.wikipedia.org/wiki/Stoicism") == "wikipedia"
    assert stage._infer_source("https://www.reddit.com/r/Stoicism/") == "forum"
    assert stage._infer_source("https://medium.com/example") == "article"
    assert stage._infer_source("https://dailystoic.com/workplace/") == "blog"


@pytest.mark.asyncio
async def test_real_research_uses_searxng_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    from src.config import Settings

    _settings = Settings()
    stage = ResearchStage(job_id="search-job", mock=False)

    async def fake_search_fixed(topic: str):
        _ = topic
        from src.models import ResearchSource

        return [
            ResearchSource(
                title="workplace stress result",
                url="https://example.com/workplace-stress",
                note="Useful summary for workplace stress.",
                relevance=0.9,
                source="web",
            )
        ]

    async def fake_llama(topic: str, sources):
        _ = topic, sources
        return {
            "title": "Workplace Stress: A Stoic Perspective",
            "key_insights": ["Insight 1", "Insight 2", "Insight 3", "Insight 4"],
            "workplace_applications": ["App 1", "App 2", "App 3", "App 4"],
        }

    monkeypatch.setattr(stage, "_search_searxng", fake_search_fixed)
    monkeypatch.setattr(stage, "_summarize_with_llama", fake_llama)
    result = await stage.run("workplace stress")

    assert result.sources
    assert "workplace stress" in result.sources[0].title.lower()
    assert result.key_insights == ["Insight 1", "Insight 2", "Insight 3", "Insight 4"]
