from pathlib import Path

import pytest

from src.config import VideoMode
from src.models import ResearchResult, ResearchSource
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

    async def fake_enrich(topic: str, sources):
        _ = topic
        return sources

    async def fake_whiskers(**kwargs):
        _ = kwargs
        return None

    monkeypatch.setattr(stage, "_search_searxng", fake_search_fixed)
    monkeypatch.setattr(stage, "_read_and_summarize_sources", fake_enrich)
    monkeypatch.setattr(stage, "_handoff_to_whiskers", fake_whiskers)
    monkeypatch.setattr(stage, "_summarize_with_llama", fake_llama)
    result = await stage.run("workplace stress")

    assert result.sources
    assert "workplace stress" in result.sources[0].title.lower()
    assert result.key_insights == ["Insight 1", "Insight 2", "Insight 3", "Insight 4"]
    assert stage.last_ledger_packet is not None
    assert stage.last_ledger_packet["topic"] == "workplace stress"


def test_search_queries_include_ledger_preferred_queries(tmp_path: Path) -> None:
    stage = ResearchStage(job_id="search-job-ledger", mock=False)
    stage.strategy_manager.project_root = tmp_path
    stage.strategy_manager.state_dir = tmp_path / "state"
    stage.strategy_manager.state_dir.mkdir(parents=True, exist_ok=True)
    stage.strategy_manager.global_strategy_path = stage.strategy_manager.state_dir / "ledger_strategy.json"
    stage.strategy_manager.build_job_packet(
        job_id="search-job-ledger",
        topic="work anxiety",
        channel=stage.channel,
        video_mode=VideoMode.SHORT,
    )
    stage.last_ledger_packet = stage.strategy_manager.load_job_packet("search-job-ledger")

    captured: list[str] = []

    async def fake_single(query: str, categories=None, topic_filter=None):
        captured.append(query)
        return []

    stage._search_searxng_single = fake_single  # type: ignore[method-assign]

    import asyncio

    asyncio.run(stage._search_searxng("work anxiety"))

    preferred = stage.last_ledger_packet["research_steering"]["preferred_queries"]
    assert captured[: len(preferred)] == preferred


@pytest.mark.asyncio
async def test_mock_research_uses_stoic_fixture_for_stoic_channel() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="mock-stoic-job", mock=True, channel=Channel.STOIC_MODERNIZED)
    result = await stage._mock_research("how to stop replaying a bad meeting at work")

    assert result.title == "How To Stop Replaying A Bad Meeting At Work: A Stoic Perspective"
    assert all("ai news" not in source.title.lower() for source in result.sources)
    assert any("control" in source.title.lower() or "marcus aurelius" in source.title.lower() for source in result.sources)
    assert any("next useful action" in item.lower() for item in result.workplace_applications)


def test_save_results_persists_whiskers_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = ResearchStage(job_id="persist-job", mock=False)
    stage.last_topic = "work anxiety"
    stage.last_ledger_packet = {"objective": "conversion"}
    stage.last_whiskers_handoff = {
        "viewer_problem": "A worker spirals before meetings.",
        "stoic_move": "Pause and separate judgment from event.",
    }

    result = ResearchResult(
        title="Work Anxiety: A Stoic Perspective",
        sources=[ResearchSource(title="Source", url="https://example.com", note="Useful note" * 20, relevance=0.9, source="web")],
        key_insights=["Insight 1", "Insight 2", "Insight 3"],
        workplace_applications=["App 1", "App 2", "App 3"],
    )

    path = stage.save_results(result)
    payload = path.read_text()

    assert '"whiskers_handoff"' in payload
    assert '"viewer_problem": "A worker spirals before meetings."' in payload


@pytest.mark.asyncio
async def test_run_replaces_rejected_topic_before_research(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = ResearchStage(job_id="replace-topic-job", mock=False)

    monkeypatch.setattr(stage, "_candidate_topics", lambda topic, limit=12: [topic, "Better Stoic Topic"])

    def fake_validate_topic(topic: str):
        return "blocked" if topic == "Rejected Topic" else None

    monkeypatch.setattr(stage, "_validate_topic_candidate", fake_validate_topic)

    seen_topics: list[str] = []

    async def fake_real_research(topic: str):
        seen_topics.append(topic)
        return ResearchResult(
            title=f"{topic}: A Stoic Perspective",
            sources=[ResearchSource(title="Source", url="https://example.com", note="Useful note" * 20, relevance=0.9, source="web")],
            key_insights=["Insight 1", "Insight 2", "Insight 3"],
            workplace_applications=["App 1", "App 2", "App 3"],
        )

    monkeypatch.setattr(stage, "_real_research", fake_real_research)
    monkeypatch.setattr(stage, "_validate_research_result", lambda topic, result: None)

    result = await stage.run("Rejected Topic")

    assert result.title == "Better Stoic Topic: A Stoic Perspective"
    assert stage.last_topic == "Better Stoic Topic"
    assert seen_topics == ["Better Stoic Topic"]


@pytest.mark.asyncio
async def test_run_retries_when_research_result_fails_validation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = ResearchStage(job_id="retry-topic-job", mock=False)
    monkeypatch.setattr(stage, "_candidate_topics", lambda topic, limit=12: [topic, "Fresh Topic"])
    monkeypatch.setattr(stage, "_validate_topic_candidate", lambda topic: None)

    seen_topics: list[str] = []

    async def fake_real_research(topic: str):
        seen_topics.append(topic)
        return ResearchResult(
            title=f"{topic}: A Stoic Perspective",
            sources=[ResearchSource(title="Source", url="https://example.com", note="Useful note" * 20, relevance=0.9, source="web")],
            key_insights=["Insight 1", "Insight 2", "Insight 3"],
            workplace_applications=["App 1", "App 2", "App 3"],
        )

    def fake_validate_result(topic: str, result: ResearchResult):
        return "too similar" if topic == "Retry Topic" else None

    monkeypatch.setattr(stage, "_real_research", fake_real_research)
    monkeypatch.setattr(stage, "_validate_research_result", fake_validate_result)

    result = await stage.run("Retry Topic")

    assert result.title == "Fresh Topic: A Stoic Perspective"
    assert stage.last_topic == "Fresh Topic"
    assert seen_topics == ["Retry Topic", "Fresh Topic"]


@pytest.mark.asyncio
async def test_real_research_limits_expensive_source_enrichment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = ResearchStage(job_id="limit-enrichment-job", mock=False)
    stage.last_ledger_packet = {"objective": "balanced", "research_steering": {"preferred_queries": []}}

    many_sources = [
        ResearchSource(
            title=f"Source {index}",
            url=f"https://example.com/{index}",
            note="Useful note " * 20,
            relevance=1 - (index * 0.01),
            source="web",
        )
        for index in range(12)
    ]

    async def fake_search(topic: str):
        _ = topic
        return many_sources

    captured: dict[str, int] = {}

    async def fake_enrich(topic: str, sources: list[ResearchSource]):
        _ = topic
        captured["count"] = len(sources)
        return sources

    async def fake_whiskers(**kwargs):
        _ = kwargs
        return None

    async def fake_llama(topic: str, sources: list[ResearchSource]):
        _ = topic, sources
        return {
            "title": "Distinct Topic: A Stoic Perspective",
            "key_insights": ["Insight 1", "Insight 2", "Insight 3", "Insight 4"],
            "workplace_applications": ["App 1", "App 2", "App 3", "App 4"],
        }

    monkeypatch.setattr(stage, "_search_searxng", fake_search)
    monkeypatch.setattr(stage, "_read_and_summarize_sources", fake_enrich)
    monkeypatch.setattr(stage, "_handoff_to_whiskers", fake_whiskers)
    monkeypatch.setattr(stage, "_summarize_with_llama", fake_llama)

    result = await stage._real_research("distinct topic")

    assert result.title == "Distinct Topic: A Stoic Perspective"
    assert captured["count"] == stage.MAX_SOURCE_ENRICHMENT
