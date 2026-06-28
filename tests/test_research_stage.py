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
    monkeypatch.setattr(stage, "_candidate_topics", lambda topic, limit=12: [topic])

    async def fake_search_fixed(topic: str):
        _ = topic
        from src.models import ResearchSource

        return [
            ResearchSource(
                title="Workplace stress from approval workflow bottlenecks",
                url="https://example.com/workplace-stress",
                note="Workplace approval queues and blocked task dependencies create workflow latency that interrupts focus and delays next actions.",
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
    result = await stage.run("approval workflow stress")

    assert result.sources
    assert "workplace stress" in result.sources[0].title.lower()
    assert result.key_insights == ["Insight 1", "Insight 2", "Insight 3", "Insight 4"]
    assert stage.last_ledger_packet is not None
    assert stage.last_topic == "approval workflow stress"


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


def test_stoic_topic_specificity_accepts_prompted_modern_work_mechanisms() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="specificity-job", mock=False, channel=Channel.STOIC_MODERNIZED)

    accepted_topics = [
        "When a Shared Drive Link Opens to Access Denied",
        "When a Failed Import Turns a Simple Task Into a Long Morning",
        "When a Noisy Workspace Turns One Email Into an Afternoon",
        "When a Coworker Takes Credit for Your Work",
        "When a Coworker's Passive Aggressive Comment Follows You Home",
        "When the Reorg Rumor Hits Team Chat, Ask for One Fact",
        "When FOMO Makes You Reply to Every Slack Ping",
        "When Office Politics Force You to Choose Sides",
    ]

    for topic in accepted_topics:
        assert stage._stoic_topic_specificity_error(topic) is None


def test_major_work_stressor_research_rejects_sports_source_drift() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="source-drift-job", mock=False, channel=Channel.STOIC_MODERNIZED)
    result = ResearchResult(
        title="When the Reorg Rumor Hits Team Chat",
        sources=[
            ResearchSource(
                title="Former Major League Baseball pitcher retires",
                url="https://en.wikinews.org/wiki/Former_Major_League_Baseball_pitcher_retires",
                note="for Team Colombia in the 2026 World Baseball Classic WBC due to a shoulder injury and team roster news",
                relevance=0.97,
                source="news",
            ),
            ResearchSource(
                title="Distraught Brazil rue what might have been",
                url="https://www.reuters.com/lifestyle/sports/example/",
                note="Brazil team suffered a World Cup loss after penalties and showed stoicism after a sports match.",
                relevance=0.96,
                source="news",
            ),
            ResearchSource(
                title="Facebook Workplace integrates with Teams",
                url="https://www.reuters.com/technology/example/",
                note="Facebook Workplace integrates with Microsoft Teams so users can share information between platforms.",
                relevance=0.95,
                source="news",
            ),
        ],
        key_insights=["sports story", "platform integration", "team mention"],
        workplace_applications=["ask for one fact", "keep a clean record"],
    )

    error = stage._stoic_operational_research_quality_error(
        "When the Reorg Rumor Hits Team Chat, Ask for One Fact",
        result,
    )

    assert error is not None
    assert "workplace" in error.lower()


def test_curated_sources_cover_major_work_stressors() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="curated-major-stressors", mock=False, channel=Channel.STOIC_MODERNIZED)

    reorg_sources = stage._curated_stoic_sources("When the Reorg Rumor Hits Team Chat, Ask for One Fact")
    fomo_sources = stage._curated_stoic_sources("When FOMO Makes You Reply to Every Slack Ping")
    conflict_sources = stage._curated_stoic_sources("When Coworker Resentment Turns a Simple Question Into a War")

    assert any("layoff" in source.note.lower() or "reorg" in source.note.lower() for source in reorg_sources)
    assert any("fomo" in source.note.lower() or "attention" in source.note.lower() for source in fomo_sources)
    assert any("conflict" in source.note.lower() or "coworker" in source.note.lower() for source in conflict_sources)


def test_major_stressor_topics_are_not_keyword_blocked() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="no-keyword-block-job", mock=False, channel=Channel.STOIC_MODERNIZED)

    assert stage._validate_topic_candidate("When FOMO Makes You Reply to Every Slack Ping") is None


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


def test_stoic_topic_specificity_allows_major_workplace_stressors() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="topic-specificity", mock=False, channel=Channel.STOIC_MODERNIZED)

    assert stage._stoic_topic_specificity_error("When the Review Comment Feels Personal") is None
    assert stage._stoic_topic_specificity_error("When FOMO Steals Your Career Focus") is None
    assert stage._stoic_topic_specificity_error("When Layoff Rumors Steal the Workday") is None
    assert stage._stoic_topic_specificity_error("When a Work Conflict Follows You Home") is None
    assert stage._stoic_topic_specificity_error("When Office Politics Makes You Perform") is None


def test_stoic_topic_specificity_accepts_source_date_range_mechanism() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="topic-specificity", mock=False, channel=Channel.STOIC_MODERNIZED)

    assert stage._stoic_topic_specificity_error("When the Source Date Range Is Missing") is None


def test_stoic_topic_specificity_accepts_status_record_and_expense_upload_mechanisms() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="topic-specificity", mock=False, channel=Channel.STOIC_MODERNIZED)

    assert stage._stoic_topic_specificity_error("When the Status Update Wants a Soft Exaggeration") is None
    assert stage._stoic_topic_specificity_error("When the Decision Record Is Incomplete") is None
    assert stage._stoic_topic_specificity_error("When the Expense Receipt Upload Times Out Again") is None
    assert stage._stoic_topic_specificity_error("When the Staging Server Times Out During Deployment") is None
    assert stage._stoic_topic_specificity_error("When the VPN Drops During the Compliance Upload") is None
    assert stage._stoic_topic_specificity_error("When One More Small Request Breaks Your Focus") is None


def test_stoic_research_candidates_do_not_reintroduce_cached_ledger_topics() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="topic-candidates", mock=False, channel=Channel.STOIC_MODERNIZED)

    assert stage._candidate_topics("When the Staging Server Times Out During Deployment") == [
        "When the Staging Server Times Out During Deployment"
    ]


def test_stoic_research_rejects_generic_self_help_source_mix() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="generic-source-guardrail", mock=False, channel=Channel.STOIC_MODERNIZED)
    result = ResearchResult(
        title="When Waiting for Approval Freezes Your Next Task",
        sources=[
            ResearchSource(
                title="Why Anxiety Feels So Real, Even When There Is No Danger",
                url="https://example.com/anxiety",
                note="This self help article explains general anxiety and emotional reactions without any approval workflow, queue, task dependency, or workplace process detail.",
                relevance=0.9,
                source="web",
            ),
            ResearchSource(
                title="Book Review: The Subtle Art of Not Giving a F*ck",
                url="https://example.com/book-review",
                note="This broad self help book review talks about caring less and emotional resilience without discussing approval queues or concrete workplace mechanisms.",
                relevance=0.85,
                source="web",
            ),
            ResearchSource(
                title="100 Performance Review Phrases To Increase Productivity",
                url="https://example.com/performance-review-phrases",
                note="A generic list of performance review phrases for managers, not evidence about blocked approval processes, workflow latency, or task handoffs.",
                relevance=0.8,
                source="web",
            ),
        ],
        key_insights=["Generic anxiety insight", "Generic review insight", "Generic self help insight"],
        workplace_applications=["Pause before reacting", "Choose what you control"],
    )

    error = stage._stoic_operational_research_quality_error("When Waiting for Approval Freezes Your Next Task", result)

    assert error is not None
    assert "generic" in error.lower() or "workplace mechanism" in error.lower()


def test_stoic_research_accepts_operational_approval_sources() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="operational-source-guardrail", mock=False, channel=Channel.STOIC_MODERNIZED)
    result = ResearchResult(
        title="When Waiting for Approval Freezes Your Next Task",
        sources=[
            ResearchSource(
                title="Approval workflow bottlenecks and blocked tasks",
                url="https://example.com/approval-workflow",
                note="Approval queues create workflow latency when a worker cannot move the next task because a sign-off dependency remains pending.",
                relevance=0.92,
                source="web",
            ),
            ResearchSource(
                title="Reducing review queue delays in team processes",
                url="https://example.com/review-queue",
                note="Team review queues and unclear approver ownership can delay decisions, increase waiting time, and interrupt focused work on dependent tasks.",
                relevance=0.88,
                source="web",
            ),
            ResearchSource(
                title="Attention residue after workplace interruptions",
                url="https://example.com/attention-residue",
                note="Workplace interruptions and pending decisions leave attention residue that makes it harder to return to deep work after context switching.",
                relevance=0.82,
                source="web",
            ),
        ],
        key_insights=["Approval queues create latency", "Waiting fragments attention", "Ownership reduces delay"],
        workplace_applications=["Name the blocked dependency", "Ask for the next approver"],
    )

    assert stage._stoic_operational_research_quality_error("When Waiting for Approval Freezes Your Next Task", result) is None


def test_stoic_research_adds_curated_noisy_workspace_sources() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="noisy-workspace", mock=False, channel=Channel.STOIC_MODERNIZED)
    sources = stage._curated_stoic_sources("When the Noisy Workspace Breaks Your Focus")
    result = ResearchResult(
        title="When the Noisy Workspace Breaks Your Focus",
        sources=sources,
        key_insights=["Noise fragments attention", "Office sound raises stress", "A small focus block is controllable"],
        workplace_applications=["Write the next tiny task", "Protect one attention block"],
    )

    assert len(sources) >= 3
    assert stage._stoic_operational_research_quality_error("When the Noisy Workspace Breaks Your Focus", result) is None


def test_stoic_research_adds_curated_printer_queue_sources() -> None:
    from src.config import Channel

    stage = ResearchStage(job_id="printer-queue", mock=False, channel=Channel.STOIC_MODERNIZED)
    sources = stage._curated_stoic_sources("When the Printer Queue Stops the Morning")
    result = ResearchResult(
        title="When the Printer Queue Stops the Morning",
        sources=sources,
        key_insights=["Printer queues are operational blockers", "Small interruptions can steal attention", "A visible next action protects focus"],
        workplace_applications=["Check the stuck job", "Communicate the delay"],
    )

    assert len(sources) >= 3
    assert stage._stoic_operational_research_quality_error("When the Printer Queue Stops the Morning", result) is None
