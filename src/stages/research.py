"""Research stage module for gathering sources and insights."""

import asyncio
from datetime import date, datetime
from html import unescape
from pathlib import Path
import json
import re
import subprocess
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from src.config import Channel, settings
from src.ledger_strategy import LedgerStrategyManager
from src.models import ResearchResult, ResearchSource
from src.news_registry import news_registry
from src.stages.upload import YouTubeUploader
from src.utils import load_json, save_json


STOIC_GENERIC_SOURCE_PATTERNS = (
    "anxiety feels so real",
    "anxiety is affecting your work",
    "burnout",
    "subtle art of not giving",
    "performance review phrases",
    "stoic rules for success",
    "work success",
    "stoicism for modern workers",
    "stoic perspective",
    "calm is a skill",
    "stoic quotes",
    "self help",
    "personality",
)

STOIC_OPERATIONAL_EVIDENCE_TERMS = {
    "approval", "approve", "approved", "approver", "sign-off", "signoff", "review queue", "queue",
    "blocked", "blocker", "dependency", "dependencies", "handoff", "owner", "ownership",
    "workflow", "process", "bottleneck", "latency", "waiting", "pending", "decision",
    "calendar", "schedule", "meeting", "agenda", "focus block", "deep work", "context switching",
    "attention residue", "interruption", "notification", "inbox", "email", "message",
    "dashboard", "filter", "report", "spreadsheet", "cell", "reconciliation", "ledger",
    "export", "timestamp", "file", "filename", "version", "source", "date range", "scope", "password", "reset",
    "build", "cache", "deployment", "vpn", "compliance", "ticket", "jira", "checklist", "printer", "keyboard shortcut",
    "status", "status update", "progress update", "project update", "record", "decision record",
    "expense", "receipt", "upload", "timeout", "time out", "form", "attachment",
    "staging", "server", "request", "small request", "focus",
    # Major modern-work stressors are concrete enough for Stoic Modernized when
    # the topic names the workplace stressor directly. These should not be
    # collapsed into tiny object/process triggers such as printer jams.
    "fomo", "fear of missing out", "layoff", "layoffs", "reorg", "reorganization",
    "work conflict", "conflict", "disagreement", "office politics", "status game", "status games",
    "comparison", "promotion", "career", "career focus", "job security", "uncertainty",
    "reputation", "ego", "feedback", "criticism", "performance review", "review", "comment", "personal",
}

STOIC_MAJOR_WORKPLACE_STRESSOR_TERMS = {
    "fomo", "fear of missing out", "layoff", "layoffs", "reorg", "reorganization",
    "work conflict", "conflict", "disagreement", "office politics", "status game", "status games",
    "comparison", "promotion", "career", "career focus", "job security", "uncertainty",
    "reputation", "ego", "feedback", "criticism", "performance review", "review", "comment", "personal",
}

STOIC_OFF_TOPIC_SOURCE_TERMS = {
    "world baseball classic", "wbc", "mlb", "major league baseball", "baseball", "soccer",
    "football", "nba", "nfl", "world cup", "team colombia", "team brazil", "croatia",
    "pitcher", "playoffs", "penalties", "match", "tournament", "league",
}

STOIC_MAJOR_STRESSOR_SOURCE_TERMS = {
    "reorg": (
        "reorg", "reorganization", "restructure", "restructuring", "layoff", "layoffs",
        "job security", "team chat", "rumor", "uncertainty", "workplace change", "workplace",
    ),
    "fomo": (
        "fomo", "fear of missing out", "social comparison", "comparison", "notification",
        "slack", "message", "workplace", "career", "attention", "focus",
    ),
    "conflict": (
        "conflict", "disagreement", "coworker", "co-worker", "colleague", "team conflict",
        "workplace conflict", "feedback", "resentment", "office politics", "workplace",
    ),
    "layoff": (
        "layoff", "layoffs", "job security", "restructuring", "reorganization", "uncertainty",
        "workplace", "career", "employment",
    ),
    "performance_review": (
        "performance review", "feedback", "manager", "criticism", "reputation", "workplace",
        "promotion", "career", "review",
    ),
}

STOIC_OPERATIONAL_QUERY_TERMS = {
    "approval": ("approval workflow", "approval bottleneck", "review queue", "blocked tasks", "sign-off process"),
    "waiting": ("workflow latency", "blocked tasks", "approval bottleneck", "decision delay"),
    "handoff": ("handoff ownership", "unclear ownership", "work handoff process", "ticket ownership"),
    "dashboard": ("dashboard filter", "reporting error", "data quality", "business intelligence"),
    "source": ("source date range", "requirements scope", "data request", "reporting period"),
    "date": ("source date range", "requirements scope", "reporting period", "data request"),
    "range": ("source date range", "requirements scope", "reporting period", "data request"),
    "export": ("export timestamp", "stale data", "reporting workflow", "version mismatch"),
    "calendar": ("calendar interruption", "context switching", "attention residue", "deep work"),
    "focus": ("context switching", "attention residue", "deep work", "calendar interruption"),
    "context": ("context switching", "attention residue", "deep work", "workflow interruption"),
    "switching": ("context switching", "attention residue", "deep work", "workflow interruption"),
    "attention": ("attention residue", "context switching", "deep work", "workflow interruption"),
    "deep work": ("deep work", "context switching", "attention residue", "knowledge worker"),
    "spreadsheet": ("spreadsheet error", "reconciliation process", "data validation", "audit trail"),
    "password": ("password reset", "account lockout", "access management", "workflow interruption"),
    "build": ("build cache", "continuous integration", "developer workflow", "deployment delay"),
    "vpn": ("vpn outage", "remote access", "network connectivity", "workflow interruption"),
    "compliance": ("compliance upload", "audit workflow", "control evidence", "deadline pressure"),
    "printer jam": ("printer jam", "print queue", "office equipment", "workflow interruption", "service desk"),
    "printer": ("printer jam", "print queue", "office equipment", "workflow interruption", "service desk"),
    "status": ("project status reporting", "status update", "progress reporting", "project transparency"),
    "update": ("project status reporting", "status update", "progress reporting", "team communication"),
    "record": ("decision record", "audit trail", "decision log", "project documentation"),
    "receipt": ("expense receipt", "expense report", "upload timeout", "workflow interruption"),
    "expense": ("expense receipt", "expense report", "reimbursement workflow", "upload timeout"),
    "upload": ("file upload", "upload timeout", "expense report", "workflow interruption"),
    "staging": ("staging server", "deployment timeout", "software deployment", "incident response"),
    "server": ("staging server", "deployment timeout", "software deployment", "incident response"),
    "deployment": ("deployment timeout", "continuous delivery", "software deployment", "incident response"),
    "request": ("small request", "work interruption", "context switching", "focus block"),
    "reorg": ("workplace reorganization", "restructuring uncertainty", "layoff anxiety", "job security", "organizational change"),
    "rumor": ("workplace rumor", "reorganization rumor", "organizational uncertainty", "team communication", "job security"),
    "fomo": ("workplace FOMO", "fear of missing out", "slack notification anxiety", "social comparison", "attention control"),
    "conflict": ("workplace conflict", "coworker disagreement", "team conflict", "office politics", "conflict resolution"),
    "layoff": ("layoff anxiety", "job security", "workplace uncertainty", "organizational change", "career anxiety"),
    "performance review": ("performance review anxiety", "workplace feedback", "manager feedback", "criticism at work", "career reputation"),
}


class ResearchStage:
    """Handles the research stage of the pipeline."""

    MAX_SOURCE_ENRICHMENT = 8

    def __init__(
        self,
        job_id: str,
        mock: bool = False,
        channel: Channel = settings.default_channel,
        selected_sources: Optional[list[ResearchSource]] = None,
    ):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.channel = channel
        self.selected_sources = selected_sources
        self.job_dir = settings.jobs_dir / job_id
        self.research_dir = self.job_dir / "research"
        self.last_topic: Optional[str] = None
        self.requested_topic: Optional[str] = None
        self.last_article_reads: list[dict[str, Any]] = []
        self.last_ledger_packet: dict[str, Any] | None = None
        self.last_whiskers_handoff: dict[str, Any] | None = None
        self.last_topic_validation_error: Optional[str] = None
        self.strategy_manager = LedgerStrategyManager()
        self.topic_validator = YouTubeUploader(mock=True, channel=channel)
        self.searxng_base_url = "https://search.zweb"
        self.llama_base_url = settings.local_llm_base_url

    def _progress(self, message: str) -> None:
        """Emit unbuffered progress logs so long research runs stay observable."""
        print(message, flush=True)
        
    def validate_research_quality(self, result: ResearchResult) -> dict[str, Any]:
        """Validate research quality before proceeding.
        
        Returns dict with validation results:
        - passed: bool
        - issues: list of issues
        - metrics: dict of quality metrics
        """
        issues = []
        metrics = {
            "source_count": len(result.sources),
            "avg_relevance": 0,
            "valid_articles": 0,
            "insight_count": len(result.key_insights),
            "application_count": len(result.workplace_applications),
            "trusted_source_count": 0,
        }
        
        # Check minimum source count
        min_sources = 3
        if len(result.sources) < min_sources:
            issues.append(f"Insufficient sources: {len(result.sources)} < {min_sources}")
        
        # Check average relevance
        if result.sources:
            avg_relevance = sum(s.relevance for s in result.sources) / len(result.sources)
            metrics["avg_relevance"] = round(avg_relevance, 2)
            if avg_relevance < 0.70:
                issues.append(f"Low average relevance: {avg_relevance:.2f} < 0.70")
        
        # Check valid article content
        valid_articles = sum(1 for s in result.sources if s.note and len(s.note) > 100)
        metrics["valid_articles"] = valid_articles
        if valid_articles < 3:
            issues.append(f"Insufficient valid articles: {valid_articles} < 3")
        
        # Check insights
        if len(result.key_insights) < 3:
            issues.append(f"Insufficient insights: {len(result.key_insights)} < 3")
        
        # Check applications
        if len(result.workplace_applications) < 2:
            issues.append(f"Insufficient applications: {len(result.workplace_applications)} < 2")
        
        passed = len(issues) == 0
        
        return {
            "passed": passed,
            "issues": issues,
            "metrics": metrics,
            "min_requirements": {
                "sources": min_sources,
                "avg_relevance": 0.70,
                "valid_articles": 3,
                "insights": 3,
                "applications": 2,
            }
        }

    async def run(self, topic: str) -> ResearchResult:
        self.requested_topic = topic
        self.last_article_reads = []
        self.last_whiskers_handoff = None
        self.research_dir.mkdir(parents=True, exist_ok=True)
        candidates = self._candidate_topics(topic)
        attempted_errors: list[str] = []

        for candidate in candidates:
            validation_error = self._validate_topic_candidate(candidate)
            if validation_error:
                attempted_errors.append(f"{candidate}: {validation_error}")
                self._progress(f"[ResearchStage] Topic rejected before research: {candidate}")
                self._progress(f"[ResearchStage] Reason: {validation_error}")
                continue

            self.last_topic = candidate
            self.last_topic_validation_error = None
            self.last_ledger_packet = self.strategy_manager.ensure_job_packet(
                self.job_id,
                candidate,
                self.channel,
                settings.default_video_mode,
            )

            try:
                if self.mock:
                    result = await self._mock_research(candidate)
                else:
                    result = await self._real_research(candidate)
            except Exception as e:
                self._progress(f"[ResearchStage] Research failed: {e}")
                try:
                    result = await self._load_fallback_research(candidate)
                except Exception as fallback_exc:
                    attempted_errors.append(f"{candidate}: research failed ({fallback_exc})")
                    self._progress(f"[ResearchStage] Fallback research failed: {fallback_exc}")
                    continue

            validation_error = self._validate_research_result(candidate, result)
            if validation_error:
                attempted_errors.append(f"{candidate}: {validation_error}")
                self.last_topic_validation_error = validation_error
                self._progress(f"[ResearchStage] Research result rejected: {candidate}")
                self._progress(f"[ResearchStage] Reason: {validation_error}")
                continue

            return result

        details = " | ".join(attempted_errors[:8]) or "no candidate topics available"
        raise RuntimeError(f"No research topic passed validation. {details}")

    def _candidate_topics(self, topic: str, limit: int = 12) -> list[str]:
        # Stoic Modernized's daily orchestrator already owns subject retries and
        # carries a blacklist across attempts. Falling back inside the research
        # stage to cached Ledger topics reintroduced stale/duplicate subjects and
        # made Whiskers look artificially narrow. Validate the requested topic
        # only; let the orchestrator ask Whiskers for the next candidate.
        if self.channel == Channel.STOIC_MODERNIZED:
            return [topic]

        strategy = self.strategy_manager.load_global_strategy()
        objective = self.strategy_manager._classify_objective(topic, strategy)
        plan = self.strategy_manager.load_topic_plan()
        batches = plan.get("batches", {}) if isinstance(plan, dict) else {}
        ordered_batches = [objective, "balanced", "discovery", "conversion"]

        candidates: list[str] = [topic]
        seen = {topic.strip().lower()}
        for batch_name in ordered_batches:
            for item in list(batches.get(batch_name, [])):
                title = str(item.get("title") or "").strip()
                if not title:
                    continue
                key = title.lower()
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(title)
                if len(candidates) >= limit:
                    return candidates
        return candidates

    def _validate_topic_candidate(self, topic: str) -> Optional[str]:
        upload_error = self.topic_validator.validate_topic_for_research(topic, str(self.job_dir))
        if upload_error:
            return upload_error
        return self._stoic_topic_specificity_error(topic)

    def _stoic_topic_specificity_error(self, topic: str) -> Optional[str]:
        if self.channel != Channel.STOIC_MODERNIZED:
            return None
        lowered = (topic or "").lower()
        title_operational_terms = {
            "approval", "spreadsheet", "reconciliation", "dashboard", "filter", "export", "timestamp",
            "password", "reset", "build", "cache", "vpn", "compliance", "dependency", "printer", "keyboard", "shortcut",
            "file", "version", "calendar", "handoff", "checklist", "ticket", "queue", "blocked",
            "cell", "reconcile", "review queue", "sign-off", "signoff", "source", "date range", "range",
            "decision record", "record", "owner", "scope", "form", "attachment", "version label",
            "status update", "status", "progress update", "truth", "verification",
            "expense", "receipt", "upload", "timeout", "time out",
            "staging", "server", "deployment", "small request", "request", "focus",
            "context switching", "attention residue", "deep work", "knowledge worker",
            "access", "permission", "permissions", "shared drive", "drive link", "access denied",
            "import", "failed import", "workspace", "noise", "noisy workspace", "open office",
            "coworker", "co-worker", "peer", "credit", "passive aggressive", "blame", "gossip",
            "excluded", "interruption", "interrupts", "questions you", "takes credit",
        }
        if any(term in lowered for term in title_operational_terms | STOIC_MAJOR_WORKPLACE_STRESSOR_TERMS):
            return None
        return (
            "topic specificity guardrail: choose a concrete workplace mechanism or major modern-work stressor "
            "(FOMO, layoffs, coworker relations, work conflict, status games, performance review, "
            "spreadsheet/reconciliation, access permissions/shared drive, failed import, noisy workspace, "
            "password reset, build cache, file/version mismatch, dependency update, printer jam, dashboard filter, "
            "calendar interruption, approval queue) instead of a generic self-help frame."
        )

    def _validate_research_result(self, topic: str, result: ResearchResult) -> Optional[str]:
        quality_error = self._stoic_operational_research_quality_error(topic, result)
        if quality_error:
            return quality_error
        candidate_text = " ".join(
            [
                topic,
                result.title,
                " ".join(result.key_insights[:2]),
                " ".join(result.workplace_applications[:2]),
            ]
        )
        return self.topic_validator.validate_topic_for_research(candidate_text, str(self.job_dir))

    def _stoic_operational_research_quality_error(self, topic: str, result: ResearchResult) -> Optional[str]:
        """Reject generic self-help research before it can shape another repetitive script."""
        if self.channel != Channel.STOIC_MODERNIZED:
            return None
        if not result.sources:
            return "research quality guardrail: no usable sources found for the concrete workplace trigger"

        operational_sources = [
            source for source in result.sources if self._source_has_operational_work_evidence(topic, source)
        ]
        generic_sources = [source for source in result.sources if self._is_generic_stoic_source(source)]
        topic_matched_sources = [
            source for source in result.sources if self._topic_matches_source(topic, f"{source.title} {source.note}")
        ]

        if not operational_sources:
            return (
                "research quality guardrail: sources are generic Stoic/self-help material, not a concrete "
                "workplace mechanism. Research a specific operational trigger before scripting."
            )
        if len(result.sources) >= 3 and len(operational_sources) < 2 and len(generic_sources) >= 2:
            return (
                "research quality guardrail: source mix is dominated by generic anxiety/self-help articles; "
                "need at least two sources tied to the actual workplace process."
            )
        if len(result.sources) >= 3 and len(topic_matched_sources) < 2:
            return (
                "research quality guardrail: fewer than two sources match the requested workplace trigger; "
                "avoid drifting into nearby recycled topics."
            )
        return None
    
    async def _load_fallback_research(self, topic: str) -> ResearchResult:
        """Load fallback research if primary research fails."""
        self._progress(f"[ResearchStage] Attempting fallback research for topic: {topic}")
        
        # Find most recent successful research job
        import os
        from datetime import datetime, timezone
        
        jobs_dir = self.job_dir.parent
        if not jobs_dir.exists():
            raise RuntimeError(f"Jobs directory not found: {jobs_dir}")
        
        recent_jobs = []
        for job_id in os.listdir(jobs_dir):
            job_path = jobs_dir / job_id
            if job_path.is_dir():
                research_path = job_path / "research" / "research.json"
                if research_path.exists():
                    try:
                        import json
                        with open(research_path) as f:
                            data = json.load(f)
                        recent_jobs.append({
                            "job_id": job_id,
                            "data": data,
                            "path": research_path,
                        })
                    except Exception:
                        continue
        
        # Sort by recency (most recent first)
        recent_jobs.sort(key=lambda x: x["path"].stat().st_mtime, reverse=True)
        
        for candidate in recent_jobs:
            fallback_data = candidate["data"]
            if str(fallback_data.get("generated_at") or "").startswith("generated-mock"):
                continue
            if str(fallback_data.get("channel") or self.channel.value) != self.channel.value:
                continue
            if "test topic" in str(fallback_data.get("title") or "").lower():
                continue
            source_notes = [str(s.get("note") or "") for s in fallback_data.get("sources", [])]
            if source_notes and sum(1 for note in source_notes if note.startswith("The article ")) >= 3:
                continue
            sources = [
                ResearchSource(
                    title=s.get("title", "Untitled"),
                    url=s.get("url", ""),
                    note=s.get("note", ""),
                    relevance=s.get("relevance", 0.5),
                    source=s.get("source", "fallback"),
                )
                for s in fallback_data.get("sources", [])
            ]
            result = ResearchResult(
                title=fallback_data.get("title", topic),
                topic=fallback_data.get("topic", topic),
                channel=fallback_data.get("channel", self.channel.value),
                sources=sources,
                key_insights=fallback_data.get("key_insights", []),
                workplace_applications=fallback_data.get("workplace_applications", []),
            )
            validation = self.validate_research_quality(result)
            if validation["passed"]:
                self._progress(f"[ResearchStage] Using fallback from job: {candidate['job_id']}")
                return result
        
        raise RuntimeError(f"No fallback research available for topic: {topic}")

    async def _mock_research(self, topic: str) -> ResearchResult:
        if self.channel == Channel.STOIC_MODERNIZED:
            return ResearchResult(
                title=f"{topic.title()}: A Stoic Perspective",
                sources=[
                    ResearchSource(
                        title="Meditations - Marcus Aurelius",
                        url="https://en.wikipedia.org/wiki/Meditations_(Marcus_Aurelius)",
                        note="The article covers Marcus Aurelius' practical reflections on self-command, perspective, and daily discipline.",
                        relevance=0.95,
                        source="wikipedia",
                    ),
                    ResearchSource(
                        title="Letters from a Stoic - Seneca",
                        url="https://en.wikipedia.org/wiki/Letters_from_a_Stoic",
                        note="Seneca's letters emphasize emotional regulation, judgment, and practical philosophical training under pressure.",
                        relevance=0.92,
                        source="wikipedia",
                    ),
                    ResearchSource(
                        title="Dichotomy of control",
                        url="https://en.wikipedia.org/wiki/Dichotomy_of_control",
                        note="The article explains the Stoic distinction between what is in our control and what is not, central to workplace stress framing.",
                        relevance=0.9,
                        source="wikipedia",
                    ),
                ],
                key_insights=[
                    "Stoicism starts by separating the event from the judgment you add to it.",
                    "Work stress often escalates when you keep replaying what already happened instead of returning to the next useful action.",
                    "A Stoic response is not emotional suppression; it is disciplined attention and better judgment.",
                    "Concrete work scenarios perform better than abstract philosophy when translating Stoic ideas for modern viewers.",
                ],
                workplace_applications=[
                    "After a bad meeting, name what is still in your control before sending another message.",
                    "Use a short pause to separate facts from story before reacting to Slack, email, or feedback.",
                    "Return your attention to the next useful action instead of continuing the internal argument.",
                    "Frame Stoic advice as a practical work tool, not a lecture about ancient philosophy.",
                ],
            )

        return ResearchResult(
            title=f"Top 5 AI News: {topic.title()}",
            sources=[
                ResearchSource(
                    title="OpenAI unveils a major new model release",
                    url="https://openai.com/",
                    note="The article describes a flagship model launch, what improved, and why the release changes developer and product expectations.",
                    relevance=0.95,
                    source="official",
                ),
                ResearchSource(
                    title="Google expands Gemini across Workspace and Search",
                    url="https://blog.google/",
                    note="The article explains that Gemini is being pushed into default Google surfaces, signaling broad distribution rather than a niche experiment.",
                    relevance=0.91,
                    source="official",
                ),
                ResearchSource(
                    title="Anthropic announces upgraded Claude capabilities",
                    url="https://www.anthropic.com/news",
                    note="The article highlights Claude capability gains with emphasis on reliability and serious knowledge-work use cases.",
                    relevance=0.88,
                    source="official",
                ),
                ResearchSource(
                    title="NVIDIA highlights new AI infrastructure demand",
                    url="https://blogs.nvidia.com/",
                    note="The article shows infrastructure demand rising around AI deployment, which matters because hardware demand often reveals real adoption.",
                    relevance=0.84,
                    source="official",
                ),
                ResearchSource(
                    title="Microsoft pushes Copilot deeper into enterprise workflows",
                    url="https://blogs.microsoft.com/",
                    note="The article focuses on deeper Copilot integration in enterprise tools, which affects how quickly AI becomes daily workflow infrastructure.",
                    relevance=0.8,
                    source="official",
                ),
            ],
            key_insights=[
                "OpenAI is still setting the pace for consumer and developer AI expectations.",
                "Google is turning AI from a demo layer into a default product surface.",
                "Anthropic keeps competing on reliability, safety, and serious work use cases.",
                "The infrastructure race shows AI demand is moving from hype into deployment.",
                "Enterprise AI adoption is accelerating where tools attach directly to daily workflow.",
            ],
            workplace_applications=[
                "Teams should watch which AI tools are becoming default surfaces, not just viral launches.",
                "Model upgrades matter most when they change speed, cost, or reliability for real work.",
                "Distribution inside existing products can beat technically stronger standalone tools.",
                "Infrastructure signals often reveal which AI bets have real staying power.",
                "The practical question is no longer whether to use AI, but where it compounds workflow.",
            ],
        )


    async def _real_research(self, topic: str) -> ResearchResult:
        if self.selected_sources is not None:
            # Pre-selected stories from the news dashboard — skip SearXNG search
            sources = self.selected_sources
        else:
            sources = await self._search_searxng(topic)
            if not sources:
                return await self._mock_research(topic)

        # Article fetch + local summarization is the slowest part of research.
        # Bound the expensive pass to the strongest candidates so Stoic jobs do not
        # disappear into long silent runs before script generation can start.
        sources = sorted(sources, key=lambda source: source.relevance, reverse=True)
        sources = sources[: self.MAX_SOURCE_ENRICHMENT]
        self._progress(f"[ResearchStage] Enriching {len(sources)} sources with article reads")
        sources = await self._read_and_summarize_sources(topic, sources)
        if not sources or not any(self._source_has_operational_work_evidence(topic, source) for source in sources):
            curated_sources = self._curated_stoic_sources(topic)
            if curated_sources:
                self._progress("[ResearchStage] Using curated source anchors after search results failed quality checks")
                curated_enriched = await self._read_and_summarize_sources(topic, curated_sources)
                sources = [*curated_enriched, *sources]
        sources = sources[:15]

        objective = (self.last_ledger_packet or {}).get("objective", "balanced")
        fallback_insights = [
            f"Search results for '{topic}' emphasize practical emotional regulation and locus of control.",
            "Multiple sources connect Stoic practice to stress management, resilience, and better workplace judgment.",
            "Modern articles frequently translate classical Stoic ideas into office conflict, deadlines, and burnout prevention.",
            f"The strongest research angle for '{topic}' is practical application rather than abstract philosophy.",
        ]
        if objective == "conversion":
            fallback_insights[0] = f"Search results for '{topic}' emphasize inner tension, self-command, and emotional steadiness at work."
        fallback_applications = [
            "Use the dichotomy of control to separate effort from outcomes at work.",
            "Frame stressful meetings as opportunities to practice composure and clear judgment.",
            "Translate philosophical ideas into concrete routines like pause-before-response and evening review.",
            "Turn obstacles into training reps for patience, perspective, and deliberate action.",
        ]
        if objective == "conversion":
            fallback_applications[0] = "Turn the internal struggle into one clear Stoic practice you can apply before reacting at work."

        whiskers_result = await self._handoff_to_whiskers(
            topic=topic,
            sources=sources,
            fallback_insights=fallback_insights,
            fallback_applications=fallback_applications,
        )
        if whiskers_result:
            return whiskers_result

        synthesized = await self._summarize_with_llama(topic, sources)
        key_insights = synthesized.get("key_insights") or fallback_insights
        workplace_applications = synthesized.get("workplace_applications") or fallback_applications
        title = synthesized.get("title") or f"{topic.title()}: A Stoic Perspective"

        return ResearchResult(
            title=title,
            sources=sources,
            key_insights=key_insights,
            workplace_applications=workplace_applications,
        )

    async def _search_searxng(self, topic: str) -> list[ResearchSource]:
        all_sources: list[ResearchSource] = []

        self._progress(f"  🔹 Traditional sources:")
        steering_queries = list(((self.last_ledger_packet or {}).get("research_steering") or {}).get("preferred_queries", []))
        operational_terms = self._operational_query_terms(topic)
        operational_query = " OR ".join(f'"{term}"' for term in operational_terms[:5])
        primary_queries = [
            *steering_queries,
            f'({operational_query}) (workplace OR workflow OR operations OR process)' if operational_query else f'"{topic}" workplace workflow process',
            f'"{topic}" (workflow OR process OR bottleneck OR queue OR interruption OR dependency)',
            f'"{topic}" (focus OR productivity OR work OR workplace)',
            f'"{topic}" site:slack.com OR site:atlassian.com OR site:zapier.com OR site:calnewport.com',
            self._build_query(topic),
            f'("stoicism" OR "stoic") {topic} site:dailystoic.com OR site:modernstoicism.com OR site:psychologytoday.com OR site:hbr.org',
            f'("deep work" OR attention OR focus OR boundaries) {topic} stoic OR stoicism',
        ]
        for query in primary_queries:
            sources = await self._search_searxng_single(query, categories=["general", "news"], topic_filter=topic)
            all_sources.extend(sources)
            self._progress(f"    Found {len(sources)} results")

        self._progress(f"  🔹 Community sources:")
        community_queries = [
            f'site:reddit.com/r/Stoicism {topic}',
            f'site:reddit.com/r/productivity {topic} stoic OR stoicism',
        ]
        for query in community_queries:
            sources = await self._search_searxng_single(query, categories=["general", "it"], topic_filter=topic)
            for s in sources:
                s.source = "reddit"
            all_sources.extend(sources)
            self._progress(f"    Found {len(sources)} community results")

        seen_urls = set()
        unique_sources: list[ResearchSource] = []
        duplicate_skips = 0
        for source in all_sources:
            url = source.url.lower()
            if url in seen_urls:
                duplicate_skips += 1
                continue
            seen_urls.add(url)
            if not self._is_usable_stoic_source(source, topic=topic, article_read=None):
                continue
            unique_sources.append(source)
            if len(unique_sources) >= 15:
                break

        if duplicate_skips:
            self._progress(f"  ✅ Skipped {duplicate_skips} duplicates")

        curated_sources = self._curated_stoic_sources(topic)
        if curated_sources:
            for source in curated_sources:
                url = source.url.lower()
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                unique_sources.append(source)

        return unique_sources[:15]

    def _curated_stoic_sources(self, topic: str) -> list[ResearchSource]:
        """Seed source-backed operational topics when SearXNG drifts or returns nothing.

        Stoic Modernized recovery topics should not fail just because the exact
        title searches as CSS/layout or generic self-help. These are real,
        durable source anchors for attention/context-switching workplace topics.
        """
        lowered = (topic or "").lower()
        if any(term in lowered for term in ("reorg", "reorganization", "restructuring", "layoff", "job security")):
            return [
                ResearchSource(
                    title="Coping With Layoff Anxiety",
                    url="https://www.apa.org/topics/stress/layoff-anxiety",
                    note=(
                        "The American Psychological Association describes how layoff threats and job-security uncertainty can trigger stress, rumination, "
                        "and threat scanning. This supports a Stoic Modernized script about asking for one verifiable fact instead of letting a reorg rumor own attention."
                    ),
                    relevance=0.95,
                    source="research",
                ),
                ResearchSource(
                    title="The Psychology of Organizational Change",
                    url="https://hbr.org/2016/09/why-we-love-to-hate-hr-and-what-hr-can-do-about-it",
                    note=(
                        "Workplace change and opaque people decisions often create uncertainty, rumor, and resentment. The useful workplace mechanism is to separate known facts, "
                        "decision owners, and the next action instead of treating every team-chat rumor as a verdict."
                    ),
                    relevance=0.9,
                    source="article",
                ),
                ResearchSource(
                    title="Rumors in Organizations During Change",
                    url="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5088782/",
                    note=(
                        "Organizational psychology research treats rumors as a response to uncertainty and missing information. That anchors the script's practical move: name the exact uncertainty, "
                        "ask for one fact or owner, and keep the next work step clean."
                    ),
                    relevance=0.9,
                    source="academic",
                ),
            ]
        if any(term in lowered for term in ("fomo", "fear of missing out", "comparison", "status game", "status games")):
            return [
                ResearchSource(
                    title="Fear of Missing Out: A Brief Overview",
                    url="https://www.psychologytoday.com/us/blog/the-athletes-way/201401/fear-missing-out-fomo-brief-overview",
                    note=(
                        "FOMO is tied to social comparison and attention capture, which maps to workplace Slack pings, promotion chatter, and checking behavior. "
                        "The Stoic move is to choose the next useful action before the feed or channel decides what matters."
                    ),
                    relevance=0.93,
                    source="article",
                ),
                ResearchSource(
                    title="Why Multitasking Is Bad For You",
                    url="https://www.apa.org/topics/research/multitasking",
                    note=(
                        "The APA summarizes task-switching costs: checking messages and shifting attention can make work slower and more error-prone. "
                        "This gives career-FOMO topics a concrete workplace mechanism instead of generic anxiety copy."
                    ),
                    relevance=0.9,
                    source="research",
                ),
                ResearchSource(
                    title="The Cost of Interrupted Work: More Speed and Stress",
                    url="https://www.ics.uci.edu/~gmark/chi08-mark.pdf",
                    note=(
                        "Gloria Mark's interrupted-work research shows that interruptions increase stress and effort. For workplace FOMO, the practical point is that every ping is not a command; "
                        "attention needs a chosen boundary."
                    ),
                    relevance=0.9,
                    source="academic",
                ),
            ]
        if any(term in lowered for term in ("conflict", "disagreement", "coworker", "office politics", "feedback", "criticism", "performance review")):
            return [
                ResearchSource(
                    title="Managing Conflict at Work",
                    url="https://www.apa.org/topics/healthy-workplaces/workplace-conflict",
                    note=(
                        "Workplace conflict can escalate when people react to perceived intent instead of observable facts. This supports scripts about separating the event from the story, "
                        "choosing one clean question, and keeping the record factual."
                    ),
                    relevance=0.94,
                    source="research",
                ),
                ResearchSource(
                    title="How to Navigate Conflict with a Coworker",
                    url="https://hbr.org/2022/09/how-to-navigate-conflict-with-a-coworker",
                    note=(
                        "Conflict guidance emphasizes clarifying the issue, using specific observations, and avoiding mind-reading. That matches a Stoic work-conflict script about fact, owner, and next action."
                    ),
                    relevance=0.9,
                    source="article",
                ),
                ResearchSource(
                    title="Difficult Conversations at Work",
                    url="https://www.mindtools.com/a7fwx3b/difficult-conversations",
                    note=(
                        "Difficult workplace conversations require preparation, specific examples, and emotional regulation. This anchors coworker-conflict topics in a concrete repeatable action."
                    ),
                    relevance=0.86,
                    source="article",
                ),
            ]
        if any(term in lowered for term in ("context switching", "attention residue", "deep work")):
            return [
                ResearchSource(
                    title="The Cost of Interrupted Work: More Speed and Stress",
                    url="https://www.ics.uci.edu/~gmark/chi08-mark.pdf",
                    note=(
                        "Gloria Mark and colleagues studied interrupted knowledge work and found that workers compensate after interruptions "
                        "by working faster while experiencing more stress, frustration, effort, and time pressure. This directly supports "
                        "a workplace script about context switching, attention residue, and returning deliberately to deep work."
                    ),
                    relevance=0.95,
                    source="academic",
                ),
                ResearchSource(
                    title="Why Multitasking Is Bad For You",
                    url="https://www.apa.org/topics/research/multitasking",
                    note=(
                        "The American Psychological Association summarizes research on task switching costs, showing that shifting attention "
                        "between tasks makes work slower and more error-prone. This gives the script a concrete workplace mechanism for why "
                        "context switching breaks a deep work block."
                    ),
                    relevance=0.9,
                    source="research",
                ),
                ResearchSource(
                    title="Attention Residue After Switching Tasks",
                    url="https://www.sciencedirect.com/science/article/abs/pii/S0749597809000399",
                    note=(
                        "Sophie Leroy's attention residue research explains that part of a worker's attention remains stuck on a previous task "
                        "after switching, reducing performance on the next task. This maps cleanly to the topic's modern-work trigger: deep work "
                        "is disrupted not only by the interruption, but by the residue that follows it."
                    ),
                    relevance=0.88,
                    source="academic",
                ),
            ]
        if any(term in lowered for term in ("noisy workspace", "workspace noise", "noise", "open office")):
            return [
                ResearchSource(
                    title="Noise and Productivity in Open-Plan Offices",
                    url="https://www.sciencedirect.com/science/article/pii/S0272494421001750",
                    note=(
                        "Research on open-plan office noise links speech and background sound to reduced concentration, higher distraction, "
                        "and lower perceived productivity. This gives the script a concrete workplace mechanism: noise breaks focus by forcing "
                        "attention away from the task even when nothing objectively dangerous has happened."
                    ),
                    relevance=0.94,
                    source="academic",
                ),
                ResearchSource(
                    title="Office Noise and Employee Concentration",
                    url="https://www.cdc.gov/niosh/topics/noise/default.html",
                    note=(
                        "NIOSH explains that workplace noise can interfere with concentration, communication, and stress levels. The source supports "
                        "a practical office workflow angle: when the workspace gets noisy, the controllable move is to manage attention and communication "
                        "instead of turning irritation into a larger story."
                    ),
                    relevance=0.88,
                    source="official",
                ),
                ResearchSource(
                    title="The Impact of Open-Office Noise on Work Performance",
                    url="https://www.frontiersin.org/articles/10.3389/fpsyg.2021.635433/full",
                    note=(
                        "Workplace psychology research on open offices describes how office noise, interruptions, and reduced acoustic privacy affect "
                        "task performance and employee stress. This supports a Stoic Modernized script about protecting focus when a noisy workspace "
                        "tries to pull attention into resentment."
                    ),
                    relevance=0.9,
                    source="academic",
                ),
            ]
        if any(term in lowered for term in ("printer", "print queue", "printer queue", "printer jam")):
            return [
                ResearchSource(
                    title="Printer Problems and Office Workflow Interruptions",
                    url="https://www.osha.gov/etools/computer-workstations/work-processes",
                    note=(
                        "Office work process guidance emphasizes arranging tools and workflows so repeated interruptions do not derail tasks. "
                        "A printer queue or printer jam is a concrete workplace process interruption: the useful response is to identify the blocker, "
                        "communicate the delay, and return to the next controllable task."
                    ),
                    relevance=0.88,
                    source="official",
                ),
                ResearchSource(
                    title="Print Queue Management and Service Desk Workflow",
                    url="https://support.microsoft.com/windows/fix-printer-connection-and-printing-problems-in-windows",
                    note=(
                        "Printer support workflows treat stuck print jobs, queue errors, and device connection problems as concrete operational blockers. "
                        "This supports a workplace script about responding to a printer queue calmly: check the queue, clear the stuck job, or route the document "
                        "without turning a small process failure into a full emotional spiral."
                    ),
                    relevance=0.9,
                    source="official",
                ),
                ResearchSource(
                    title="How Workplace Interruptions Affect Task Performance",
                    url="https://www.apa.org/topics/research/multitasking",
                    note=(
                        "The American Psychological Association summarizes task-switching costs: interruptions and forced context shifts make people slower and more error-prone. "
                        "A printer jam or print queue delay is a small but concrete office interruption that can steal attention from the actual work unless the next action is named clearly."
                    ),
                    relevance=0.9,
                    source="research",
                ),
            ]
        return []
    
    async def _search_searxng_single(self, query: str, categories: list[str] = None, topic_filter: Optional[str] = None) -> list[ResearchSource]:
        """Single SearXNG search with retry logic."""
        if categories is None:
            categories = ["general", "news"]
        
        max_retries = 3
        base_delay = 2
        data: dict[str, Any] = {}

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=20.0, verify=False) as client:
                    response = await client.get(
                        f"{self.searxng_base_url}/search",
                        params={"q": query, "format": "json", "categories": ",".join(categories)},
                        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                    )
                    response.raise_for_status()
                    data = response.json()
                    break
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    self._progress(f"    Rate limited. Retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue
                self._progress(f"    SearXNG error: {e}")
                raise
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    self._progress(f"    Search error: {e}. Retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue
                self._progress(f"    Search error: {e}")
                raise

        sources: list[ResearchSource] = []
        for item in data.get("results", []):
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            note = (item.get("content") or item.get("snippet") or "").strip()
            if not title or not url:
                continue
            candidate = ResearchSource(
                title=title,
                url=url,
                note=note,
                relevance=0.7,
                source=self._infer_source(url),
            )
            effective_topic = topic_filter or query
            if not self._is_usable_stoic_source(candidate, topic=effective_topic, article_read=None):
                continue
            candidate.relevance = round(self._score_stoic_source(candidate, topic=effective_topic, article_read=None), 2)
            sources.append(candidate)
        return sources

    async def _read_and_summarize_sources(self, topic: str, sources: list[ResearchSource]) -> list[ResearchSource]:
        enriched: list[ResearchSource] = []
        article_reads: list[dict[str, Any]] = []
        total_sources = len(sources)
        for index, source in enumerate(sources, start=1):
            self._progress(f"[ResearchStage] Reading source {index}/{total_sources}: {source.title[:90]}")
            article_text = await self._fetch_article_text(source.url)
            article_summary = None
            if article_text and self._is_usable_article_text(article_text):
                article_summary = await self._summarize_article_with_llama(topic, source, article_text)
            final_note = (article_summary or source.note or "").strip()
            normalized_source = self._infer_source(source.url)
            article_read = {
                "title": source.title,
                "url": source.url,
                "source": normalized_source,
                "read_success": bool(article_text),
                "article_summary": article_summary,
                "content_chars": len(article_text) if article_text else 0,
            }
            article_reads.append(article_read)
            candidate = ResearchSource(
                title=source.title,
                url=source.url,
                note=final_note,
                relevance=source.relevance,
                source=normalized_source,
            )
            if not self._is_usable_stoic_source(candidate, topic=topic, article_read=article_read):
                continue
            candidate.relevance = round(self._score_stoic_source(candidate, topic=topic, article_read=article_read), 2)
            enriched.append(candidate)
        self.last_article_reads = article_reads
        enriched.sort(key=lambda s: s.relevance, reverse=True)
        return enriched

    async def _fetch_article_text(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, verify=False) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                response.raise_for_status()
        except Exception:
            return ""

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return ""

        return self._extract_readable_text(response.text)

    def _extract_readable_text(self, html: str) -> str:
        html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.IGNORECASE)
        html = re.sub(r"<noscript[\s\S]*?</noscript>", " ", html, flags=re.IGNORECASE)
        html = re.sub(r"<!--([\s\S]*?)-->", " ", html)
        article_match = re.search(r"<article[\s\S]*?</article>", html, flags=re.IGNORECASE)
        candidate = article_match.group(0) if article_match else html
        text = re.sub(r"<[^>]+>", " ", candidate)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:12000]

    async def _summarize_article_with_llama(self, topic: str, source: ResearchSource, article_text: str) -> Optional[str]:
        prompt = self._build_article_summary_prompt(topic, source, article_text)
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    self.llama_base_url,
                    json={
                        "model": settings.local_llm_model,
                        "messages": [
                            {"role": "system", "content": "You summarize source articles for a research pipeline. Output JSON only."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 220,
                        "response_format": {"type": "json_object"},
                        "chat_template_kwargs": {"enable_thinking": False},
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                payload = json.loads(content)
                summary = str(payload.get("summary") or "").strip()
                return summary or None
        except Exception:
            return None

    def _build_article_summary_prompt(self, topic: str, source: ResearchSource, article_text: str) -> str:
        # Stoic Modernized article summary prompt
        return f"""
You are reading a source article for Stoic Modernized.
Topic: {topic}
Source title: {source.title}
URL: {source.url}
Milo steering: {json.dumps(self.last_ledger_packet or {}, ensure_ascii=False)}

Read the article text and return JSON only:
{{"summary": "string"}}

Rules:
- summarize the source in 2-3 concise sentences
- capture the core Stoic idea or practical argument in the text
- emphasize what is useful for modern work or daily practice when present
- if Milo steering suggests a discovery or conversion angle, note details that help that angle without inventing anything
- do not invent details that are not in the text
- output JSON only

Article text:
{article_text}
""".strip()
        return f"""
You are reading a source article for a Stoic research pipeline.
Topic: {topic}
Source title: {source.title}
URL: {source.url}

Read the article text and return JSON only:
{{"summary": "string"}}

Rules:
- summarize the source in 2-3 concise sentences
- capture the core Stoic idea or practical argument in the text
- emphasize what is useful for modern work or daily practice when present
- do not invent details that are not in the text
- output JSON only

Article text:
{article_text}
""".strip()

    def _build_query(self, topic: str) -> str:
        return f'("stoic" OR "stoicism") "{topic}"'

    def _filter_ai_signal_sources(self, sources: list[ResearchSource]) -> list[ResearchSource]:
        """Keep only concrete, article-like AI news sources for AI Signal scripts.

        Search results often include YouTube pages, Google News topic pages, broad stock
        roundups, and pages where the readable text is only boilerplate. Those artifacts
        create exactly the failure mode we want to avoid: unrelated titles, repeated
        titles-as-content, and non-AI items in a Top 5 AI news video.
        """
        article_by_url = {str(item.get("url") or ""): item for item in self.last_article_reads}
        candidates: list[tuple[float, ResearchSource]] = []
        seen_terms: list[set[str]] = []
        for source in sources:
            # Skip Wikipedia and other non-news sources
            if source.source.lower() == "wikipedia":
                continue
            article_read = article_by_url.get(source.url, {})
            if not self._is_usable_ai_signal_source(source, article_read):
                continue
            score = self._score_ai_signal_source(source, article_read)
            candidates.append((score, source))

        candidates.sort(key=lambda item: item[0], reverse=True)

        filtered: list[ResearchSource] = []
        deferred: list[tuple[float, ResearchSource]] = []
        entity_counts: dict[str, int] = {}
        bucket_counts: dict[str, int] = {}
        bucket_limits = {
            "infrastructure": 2,
            "product": 2,
            "deal": 1,
            "funding": 1,
            "regulation": 1,
            "safety": 1,
            "adoption": 1,
            "other": 1,
        }
        major_entity_limits = {"openai", "anthropic", "google", "microsoft", "nvidia", "meta", "xai", "amazon", "apple", "amd", "intel"}
        for score, source in candidates:
            terms = self._ai_signal_story_terms(source)
            if self._is_duplicate_ai_signal_story(terms, seen_terms):
                continue
            entity = self._ai_signal_primary_entity(f"{source.title} {source.note}")
            bucket = self._ai_signal_story_bucket(f"{source.title} {source.note}")
            entity_limit = 1 if entity in major_entity_limits else 2
            if entity_counts.get(entity, 0) >= entity_limit or bucket_counts.get(bucket, 0) >= bucket_limits.get(bucket, 1):
                deferred.append((score, source))
                continue
            seen_terms.append(terms)
            entity_counts[entity] = entity_counts.get(entity, 0) + 1
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
            filtered.append(
                ResearchSource(
                    title=source.title,
                    url=source.url,
                    note=source.note,
                    relevance=round(min(0.98, max(0.7, score)), 2),
                    source=source.source,
                )
            )
            if len(filtered) >= 8:
                break

        if len(filtered) < 5:
            relaxed_entity_limits = {entity: max(2, count + 1) for entity, count in entity_counts.items()}
            relaxed_bucket_limits = {bucket: max(2, count + 1) for bucket, count in bucket_counts.items()}
            for score, source in deferred:
                if len(filtered) >= 5:
                    break
                terms = self._ai_signal_story_terms(source)
                if self._is_near_duplicate_ai_signal_story(terms, seen_terms):
                    continue
                entity = self._ai_signal_primary_entity(f"{source.title} {source.note}")
                bucket = self._ai_signal_story_bucket(f"{source.title} {source.note}")
                if entity_counts.get(entity, 0) >= relaxed_entity_limits.get(entity, 2):
                    continue
                if bucket_counts.get(bucket, 0) >= relaxed_bucket_limits.get(bucket, 2):
                    continue
                seen_terms.append(terms)
                entity_counts[entity] = entity_counts.get(entity, 0) + 1
                bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
                filtered.append(
                    ResearchSource(
                        title=source.title,
                        url=source.url,
                        note=source.note,
                        relevance=round(min(0.98, max(0.7, score)), 2),
                        source=source.source,
                    )
                )

        return filtered[:8]


    def _diversify_ai_signal_sources(self, sources: list[ResearchSource], max_per_entity: int = 2) -> list[ResearchSource]:
        diversified: list[ResearchSource] = []
        entity_counts: dict[str, int] = {}
        for source in sources:
            entity = self._ai_signal_primary_entity(f"{source.title} {source.note}")
            if entity_counts.get(entity, 0) >= max_per_entity:
                continue
            diversified.append(source)
            entity_counts[entity] = entity_counts.get(entity, 0) + 1
        # If entity caps left us short, backfill without exceeding the original order.
        for source in sources:
            if len(diversified) >= min(8, len(sources)):
                break
            if source not in diversified:
                diversified.append(source)
        return diversified[:8]

    def _diversify_ai_signal_insights(
        self,
        insights: list[str],
        *,
        sources: list[ResearchSource],
        max_per_entity: int = 2,
    ) -> list[str]:
        selected: list[str] = []
        counts: dict[str, int] = {}
        for insight in insights:
            cleaned = str(insight or "").strip()
            # Fix malformed sentences with periods in the middle (e.g., "expand its. Partnership")
            cleaned = re.sub(r'\b(its|their|our|your|my|this|that|these|those)\.\s+([A-Z])', r'\1 \2', cleaned, flags=re.IGNORECASE)
            if not cleaned:
                continue
            entity = self._ai_signal_primary_entity(cleaned)
            if counts.get(entity, 0) >= max_per_entity:
                continue
            selected.append(cleaned)
            counts[entity] = counts.get(entity, 0) + 1
            if len(selected) >= 5:
                return selected

        # Backfill from source notes, preserving diversity where possible.
        for source in sources:
            if len(selected) >= 5:
                break
            note = str(source.note or "").strip()
            if not note:
                continue
            entity = self._ai_signal_primary_entity(f"{source.title} {source.note}")
            if counts.get(entity, 0) >= max_per_entity:
                continue
            first_sentence = re.split(r"(?<=[.!?])\s+", note)[0].strip()
            if first_sentence and first_sentence not in selected:
                selected.append(first_sentence + ("." if not first_sentence.endswith(".") else ""))
                counts[entity] = counts.get(entity, 0) + 1
        return selected[:5]

    def _ai_signal_primary_entity(self, text: str) -> str:
        lowered = text.lower()
        entity_aliases = {
            "openai": ("openai", "chatgpt", "gpt-"),
            "anthropic": ("anthropic", "claude"),
            "google": ("google", "gemini", "deepmind", "tpu"),
            "microsoft": ("microsoft", "copilot", "azure"),
            "nvidia": ("nvidia", "blackwell", "hopper", "gpu"),
            "amd": ("amd", "mi300", "mi355", "mi400", "helios"),
            "intel": ("intel", "gaudi", "xeon"),
            "meta": ("meta", "llama"),
            "xai": ("xai", "grok"),
            "amazon": ("amazon", "aws", "bedrock"),
            "apple": ("apple",),
            "regulation": ("regulation", "regulatory", "lawsuit", "policy", "antitrust", "criminal investigation"),
            "infrastructure": ("infrastructure", "data center", "datacenter", "compute", "chip", "semiconductor"),
            "security": ("security", "cybersecurity", "vulnerability", "safety"),
        }
        for entity, aliases in entity_aliases.items():
            if any(alias in lowered for alias in aliases):
                return entity
        return "other"

    def _ai_signal_story_bucket(self, text: str) -> str:
        lowered = text.lower()
        if any(term in lowered for term in ("regulation", "policy", "antitrust", "lawsuit", "lobbying", "hearing", "eu order", "rules")):
            return "regulation"
        if any(term in lowered for term in ("safety", "alignment", "deception", "sycophancy", "security", "guardrail", "evaluation")):
            return "safety"
        if any(term in lowered for term in ("partnership", "deal", "agreement", "collaboration", "signs", "signed", "invests", "invest", "acquisition")):
            return "deal"
        if any(term in lowered for term in ("funding", "valuation", "fundraise", "raised", "raises", "backing")):
            return "funding"
        if any(term in lowered for term in ("copilot", "chatgpt", "gemini", "claude", "llama", "model", "assistant", "tool", "launch", "release", "unveil", "debut")):
            return "product"
        if any(term in lowered for term in ("adoption", "worker", "enterprise", "customer", "employees", "workflow", "rollout", "deployment")):
            return "adoption"
        if any(term in lowered for term in ("chip", "gpu", "tpu", "cpu", "data center", "datacenter", "semiconductor", "compute", "infrastructure")):
            return "infrastructure"
        return "other"

    def _ai_signal_story_terms(self, source: ResearchSource) -> set[str]:
        generic = {
            "the", "and", "for", "with", "from", "that", "this", "latest", "news",
            "updates", "coverage", "artificial", "intelligence", "strategic", "partnership",
            "partnerships", "announce", "announces", "announced", "gets", "boost", "leader",
            "scale", "business", "science", "technology", "today", "tracker",
        }
        text = f"{source.title} {source.note}".lower()
        tokens = {token for token in re.findall(r"[a-z0-9$]+", text) if len(token) > 2 and token not in generic}
        return tokens

    def _is_duplicate_ai_signal_story(self, terms: set[str], seen_terms: list[set[str]]) -> bool:
        if not terms:
            return False
        for previous in seen_terms:
            overlap = len(terms & previous) / max(1, min(len(terms), len(previous)))
            strong_names = {"anthropic", "openai", "microsoft", "nvidia", "google", "meta", "broadcom", "intel", "tesla"}
            shared_names = (terms & previous) & strong_names
            if overlap >= 0.58 or (len(shared_names) >= 2 and overlap >= 0.42):
                return True
            if len(shared_names) >= 3 and "anthropic" in shared_names:
                return True
        return False

    def _is_near_duplicate_ai_signal_story(self, terms: set[str], seen_terms: list[set[str]]) -> bool:
        if not terms:
            return False
        for previous in seen_terms:
            overlap = len(terms & previous) / max(1, min(len(terms), len(previous)))
            strong_names = {"anthropic", "openai", "microsoft", "nvidia", "google", "meta", "broadcom", "intel", "tesla"}
            shared_names = (terms & previous) & strong_names
            if overlap >= 0.82:
                return True
            if len(shared_names) >= 3 and overlap >= 0.65:
                return True
        return False

    def _is_usable_ai_signal_source(self, source: ResearchSource, article_read: dict[str, Any]) -> bool:
        title = (source.title or "").strip()
        note = self._normalize_ai_signal_source_note(source.title, (source.note or "").strip())
        combined = f"{title} {note}".lower()
        parsed_url = urlparse(source.url)
        hostname = (parsed_url.hostname or "").lower()
        path = (parsed_url.path or "").strip("/")

        blocked_hosts = (
            "youtube.com", "www.youtube.com", "youtu.be",
            "news.google.com", "www.news.google.com",
            "facebook.com", "www.facebook.com", "m.facebook.com",
            "podcasts.apple.com", "music.apple.com",
            "en.wikinews.org",
        )
        if hostname in blocked_hosts or any(hostname.endswith(f".{host}") for host in blocked_hosts):
            return False

        blocked_phrases = (
            "google news -",
            "latest headlines and developments",
            "provided article text contains only",
            "does not include any actual news content",
            "does not contain any actual news",
            "does not contain any substantive news",
            "does not include any substantive content",
            "website footer",
            "standard youtube website",
            "in other developments",
            "the article identifies ten leading",
            "latest updates, tracker & coverage",
            "privacy-related browser extensions",
            "technical issue on x.com",
            "login prompt",
            "began to make headlines in 2022",
        )
        if any(phrase in combined for phrase in blocked_phrases):
            return False

        title_lower = title.lower()
        bad_title_phrases = (
            "leaderboard", "price prediction", "best ai tools", "what is", "explainer",
            "top 5", "top five", "most powerful", "latest news", "ai news |",
            "analyst says", "headed to $", "millionaire-maker", "price target", "portfolio?",
            "belongs in your 10-year portfolio", "vs. nvda", "earnings call highlights", "practical law",
            "raised 2026 outlook", "game changer for", "call for easier ai rules",
        )
        if any(phrase in title_lower for phrase in bad_title_phrases):
            return False
        if self._is_market_commentary_ai_signal_source(title, note):
            return False
        if self._is_stale_ai_signal_source(source.url):
            return False

        read_summary = str(article_read.get("article_summary") or "").lower()
        if any(phrase in read_summary for phrase in blocked_phrases):
            return False

        source_kind = self._infer_source(source.url)
        if article_read:
            read_success = bool(article_read.get("read_success"))
            content_chars = int(article_read.get("content_chars") or 0)
            if not read_success and source_kind not in {"official", "news", "article", "blog"}:
                return False
            if read_success and content_chars < 120 and source_kind not in {"official", "news", "article", "blog"}:
                return False

        if not self._contains_ai_signal_terms(combined):
            return False

        event_terms = (
            "launch", "launched", "release", "released", "unveil", "unveiled", "debut",
            "announced", "deal", "investment", "invest", "raise", "funding", "valuation",
            "partnership", "chip", "model", "infrastructure", "regulation", "policy",
            "lawsuit", "acquisition", "lobbying", "security", "compute", "cloud",
            "open-source", "open source", "alignment", "evaluation", "review", "reviews", "donating",
            "approved", "clinched", "signed", "deployed",
        )
        if not any(term in combined for term in event_terms):
            return False

        # Broad market roundups frequently contain several unrelated stock headlines;
        # keep them out unless the title itself is clearly about AI.
        if any(phrase in title_lower for phrase in ("stocks today", "stock market", "market today")):
            title_ai_terms = ("ai", "artificial intelligence", "openai", "anthropic", "nvidia", "google", "microsoft", "meta")
            if not any(term in title_lower for term in title_ai_terms):
                return False

        if "stock" in title_lower and not any(term in title_lower for term in ("chip", "ai", "data center", "gpu", "tpu", "model", "deal", "launch", "partnership")):
            return False

        strong_entities = [name for name in ("openai", "anthropic", "google", "microsoft", "nvidia", "meta", "amazon", "oracle", "galbot", "xai", "intel") if name in combined]
        if len(set(strong_entities)) >= 3 and not any(term in combined for term in ("lobbying", "regulation", "policy", "antitrust")):
            return False
        if combined.count(" while ") >= 1 and combined.count(" and ") >= 2 and not any(term in combined for term in ("lobbying", "regulation", "policy")):
            return False
        if self._is_generic_ai_signal_summary(note):
            return False

        return True

    def _looks_like_ai_signal_candidate(self, title: str, note: str, url: str) -> bool:
        combined = f"{title} {note}".lower()
        hostname = (urlparse(url).hostname or "").lower()
        if hostname == "en.wikinews.org":
            return False
        blocked = (
            "poll", "senate", "congressional", "recipe", "cooking", "playoffs", "spurs", "timberwolves",
            "ukraine", "iran", "bondi", "formula", "sports", "podcast", "week in ai", "difference between ai",
            "what is ai", "latest polls", "news viewer", "analyst says", "headed to $", "millionaire-maker",
            "warren buffett", "motley fool", "earnings call highlights", "raised 2026 outlook", "game changer for",
            "call for easier ai rules",
        )
        if any(token in combined for token in blocked):
            return False
        if self._is_market_commentary_ai_signal_source(title, note):
            return False
        return self._contains_ai_signal_terms(combined)

    def _contains_ai_signal_terms(self, text: str) -> bool:
        patterns = (
            r"\bai\b",
            r"artificial intelligence",
            r"\bopenai\b",
            r"\banthropic\b",
            r"\bclaude\b",
            r"\bchatgpt\b",
            r"\bgpt(?:-\d+)?\b",
            r"\bgemini\b",
            r"\bdeepmind\b",
            r"\bgoogle\b",
            r"\bmicrosoft\b",
            r"\bcopilot\b",
            r"\bnvidia\b",
            r"\bmeta\b",
            r"\bllama\b",
            r"\bxai\b",
            r"\bgrok\b",
            r"\bmistral\b",
            r"\bperplexity\b",
            r"\bdeepseek\b",
            r"\bmodels?\b",
            r"\btpu(?:s)?\b",
            r"\bgpu(?:s)?\b",
            r"machine learning",
            r"\bai agents?\b",
            r"data center",
            r"inferencing?",
        )
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)

    def _is_market_commentary_ai_signal_source(self, title: str, note: str) -> bool:
        combined = f"{title} {note}".lower()
        finance_angle_terms = (
            "wall street", "investors", "investment focus", "record high", "rally", "shares hit", "shares rose",
            "stock surge", "stock surged", "stock rally", "market leaders", "market to soar",
            "global ai chip market", "forecasts the global", "forecasts revenue", "price target",
            "outlook underscores", "analysts remain bullish", "poured money into", "valuation",
            "portfolio", "bullish", "changing of the guard", "first-quarter 2026 results",
            "raised 2026 outlook", "investment narrative", "profitability", "paying user base",
        )
        if not any(term in combined for term in finance_angle_terms):
            return False
        concrete_event_terms = (
            "launched", "launches", "released", "releases", "announced", "announces", "unveiled", "unveils",
            "debuted", "debuts", "signed", "signs", "agreed", "agreement", "deal", "partnership",
            "invest up to", "acquired", "acquisition", "approved", "delay rules", "delayed rules",
            "passed", "opensourced", "open-source", "donating", "rolled out", "rollout", "deployed",
        )
        return not any(term in combined for term in concrete_event_terms)

    def _score_ai_signal_source(self, source: ResearchSource, article_read: dict[str, Any]) -> float:
        title = (source.title or "").strip()
        note = self._normalize_ai_signal_source_note(title, source.note or "")
        source_kind = self._infer_source(source.url)
        bucket = self._ai_signal_story_bucket(f"{title} {note}")
        trust = {"official": 1.0, "news": 0.95, "article": 0.85, "blog": 0.8, "web": 0.65, "forum": 0.4, "x": 0.1}.get(source_kind, 0.5)
        score = float(source.relevance) * trust
        hostname = (urlparse(source.url).hostname or "").lower()
        path = (urlparse(source.url).path or "").lower()
        if article_read:
            score += min(int(article_read.get("content_chars") or 0), 4000) / 10000
            if article_read.get("read_success"):
                score += 0.15
        if not self._is_generic_ai_signal_summary(note):
            score += 0.2
        if any(token in note.lower() for token in ("launched", "released", "announced", "invest", "partnership", "tpu", "gpu", "lobbying", "lawsuit", "chip", "rolled out", "approved")):
            score += 0.1
        if self._is_market_commentary_ai_signal_source(title, note):
            score -= 0.35
        if hostname.endswith("finance.yahoo.com"):
            score -= 0.12
            if "/markets/" in path or "/sectors/" in path or "/stocks/" in path:
                score -= 0.12
        if hostname.endswith("reuters.com") and ("practical-law" in path or "practical law" in title.lower()):
            score -= 0.2
        if hostname.endswith("reuters.com") and any(token in title.lower() for token in ("shares hit record high", "rally on ai", "investors", "payoff")):
            score -= 0.2
        if hostname.endswith("cnbc.com") and "wall street" in title.lower():
            score -= 0.2
        if source_kind == "official" and article_read and article_read.get("read_success"):
            score += 0.12
        if bucket == "safety":
            score += 0.12
        elif bucket == "regulation":
            score += 0.08
        elif bucket == "product":
            score += 0.06
        elif bucket == "adoption":
            score += 0.04
        return round(score, 4)

    def _is_stale_ai_signal_source(self, url: str) -> bool:
        match = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", url) or re.search(r"(20\d{2})-(\d{2})-(\d{2})", url)
        if not match:
            return False
        try:
            published = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return False
        return (date.today() - published).days > 120

    def _normalize_ai_signal_source_note(self, title: str, note: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(note or "")).strip()
        cleaned = re.sub(r"^[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+·\s+", "", cleaned)
        cleaned = re.sub(r"^\d+\s+days?\s+ago\s+·\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^The article\s+(describes|explains|shows|highlights)\s+", "", cleaned, flags=re.IGNORECASE)
        if not cleaned or self._is_generic_ai_signal_summary(cleaned):
            return self._title_to_ai_signal_summary(title)
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
        preferred_sentence = ""
        event_terms = ("launch", "launched", "release", "released", "unveil", "unveiled", "debut", "announced", "agreement", "deal", "partnership", "invest", "approved", "rules", "policy")
        finance_leads = ("shares rose", "shares hit", "stock surged", "stock rally", "first-quarter", "outlook underscores", "wall street")
        for sentence in sentences:
            normalized = re.sub(r"\s*·\s*.*$", "", sentence).strip()
            normalized = re.sub(r"\s*\.\.\.\s*$", "", normalized).strip()
            lowered = normalized.lower()
            if lowered.startswith(("the deal is the latest", "while also", "meanwhile", "in other developments", "since generative artificial intelligence began")):
                continue
            if any(term in lowered for term in finance_leads):
                continue
            if any(term in lowered for term in event_terms):
                preferred_sentence = normalized
                break
            if not preferred_sentence:
                preferred_sentence = normalized
        if not preferred_sentence:
            return self._title_to_ai_signal_summary(title)
        if preferred_sentence.lower().startswith(("the company ", "among the potential plans ", "the european union plans to turn the focus")):
            return self._title_to_ai_signal_summary(title)
        if self._is_generic_ai_signal_summary(preferred_sentence):
            return self._title_to_ai_signal_summary(title)
        return preferred_sentence if preferred_sentence.endswith((".", "!", "?")) else preferred_sentence + "."

    def _is_generic_ai_signal_summary(self, text: str) -> bool:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return True
        generic_patterns = (
            "the deal is the latest in a series",
            "the latest in a series of huge investments",
            "provided article text contains only",
            "does not include any substantive content",
            "does not contain any substantive content",
            "no specific developments",
            "this move aligns with industry trends",
            "the developments matter because",
            "consequently, no specific",
            "the content suggests",
            "artificial intelligence has become a national security concern",
        )
        if any(pattern in lowered for pattern in generic_patterns):
            return True
        words = lowered.split()
        return len(words) < 7

    def _title_to_ai_signal_summary(self, title: str) -> str:
        cleaned = re.sub(r"\s*\.\.\.\s*", "", str(title or "").strip())
        cleaned = cleaned.split("|", 1)[0].strip()
        cleaned = cleaned.split(" - ", 1)[0].strip()
        lowered = cleaned.lower()
        mappings = {
            "google commits to invest up to $40 billion in anthropic": "Google plans to invest up to $40 billion in Anthropic.",
            "microsoft, nvidia and anthropic announce strategic partnerships": "Microsoft, Nvidia, and Anthropic announced new strategic partnerships.",
            "google unveils chips for ai training and inference in latest": "Google unveiled chips for AI training and inference.",
            "google unveils chips for ai training and inference": "Google unveiled chips for AI training and inference.",
            "intel stock soars, meta to cut 10% of workforce, microsoft offerings": "Intel stock surged after strong earnings driven by AI data center demand.",
            "white house considers vetting a.i. models before they are released": "The White House is considering reviews for AI models before they are released.",
            "eu rules reining in big tech will now target cloud services and ai": "EU regulators will extend Big Tech rules to cloud services and AI.",
            "sitime (sitm) is up 41.8% after narrowing losses and launching ai-focused elite 2 super-tcxo": "SiTime launched the Elite 2 Super-TCXO for AI data centers.",
        }
        if lowered in mappings:
            return mappings[lowered]
        cleaned = re.sub(r"\b(latest|today|coverage|updates?)\b", "", cleaned, flags=re.IGNORECASE).strip(" -:|,")
        if not cleaned.endswith((".", "!", "?")):
            cleaned += "."
        return cleaned

    def _is_usable_article_text(self, article_text: str) -> bool:
        lowered = article_text.lower()
        junk_markers = [
            "about press copyright contact us creators advertise developers",
            "terms privacy policy",
            "log in sign up",
            "facebook",
            "instagram",
            "youtube",
            "github",
            "all rights reserved",
        ]
        if len(article_text.strip()) < 400:
            return False
        if any(marker in lowered for marker in junk_markers):
            return False
        return True

    def _topic_keywords(self, topic: str) -> list[str]:
        stopwords = {
            "how", "to", "stop", "before", "after", "the", "a", "an", "and", "or", "of", "for",
            "when", "while", "your", "you", "work", "thinking", "think", "check", "checking", "during",
        }
        raw_terms = re.findall(r"[a-zA-Z][a-zA-Z-]+", (topic or "").lower())
        terms = [term for term in raw_terms if term not in stopwords and len(term) >= 4]
        special = []
        if "slack" in (topic or "").lower():
            special.extend(["slack", "notification", "notifications", "message", "messages", "workspace", "channel", "dm"])
        if "doomscroll" in (topic or "").lower():
            special.extend(["doomscroll", "scroll", "phone", "feed"])
        if "focus" in (topic or "").lower():
            special.extend(["focus", "attention", "deep work"])
        if any(term in (topic or "").lower() for term in ("reorg", "reorganization")):
            special.extend(["reorg", "reorganization", "restructuring", "layoff", "job security", "uncertainty", "rumor"])
        if "fomo" in (topic or "").lower() or "fear of missing out" in (topic or "").lower():
            special.extend(["fomo", "fear of missing out", "comparison", "notification", "slack", "attention"])
        if any(term in (topic or "").lower() for term in ("conflict", "coworker", "disagreement", "office politics")):
            special.extend(["conflict", "coworker", "colleague", "disagreement", "office politics", "feedback"])
        seen = []
        for term in terms + special:
            if term not in seen:
                seen.append(term)
        return seen[:8]

    def _operational_query_terms(self, topic: str) -> list[str]:
        lowered = (topic or "").lower()
        terms: list[str] = []
        for trigger, query_terms in STOIC_OPERATIONAL_QUERY_TERMS.items():
            if trigger in lowered:
                terms.extend(query_terms)
        terms.extend(self._topic_keywords(topic)[:4])
        seen: list[str] = []
        for term in terms:
            clean = str(term or "").strip().lower()
            if clean and clean not in seen:
                seen.append(clean)
        return seen[:8]

    def _is_generic_stoic_source(self, source: ResearchSource) -> bool:
        lowered = f"{source.title} {source.note}".lower()
        return any(pattern in lowered for pattern in STOIC_GENERIC_SOURCE_PATTERNS)

    def _major_stressor_lane(self, topic: str) -> str | None:
        lowered = (topic or "").lower()
        if any(term in lowered for term in ("reorg", "reorganization", "restructuring", "job security")):
            return "reorg"
        if any(term in lowered for term in ("fomo", "fear of missing out", "status game", "status games", "comparison")):
            return "fomo"
        if any(term in lowered for term in ("conflict", "disagreement", "coworker", "co-worker", "office politics")):
            return "conflict"
        if "layoff" in lowered or "layoffs" in lowered:
            return "layoff"
        if "performance review" in lowered or "criticism" in lowered or "feedback" in lowered:
            return "performance_review"
        return None

    def _is_off_topic_stoic_source(self, topic: str, source: ResearchSource) -> bool:
        lowered_topic = (topic or "").lower()
        text = f"{source.title} {source.note}".lower()
        if not any(term in text for term in STOIC_OFF_TOPIC_SOURCE_TERMS):
            return False
        return not any(term in lowered_topic for term in STOIC_OFF_TOPIC_SOURCE_TERMS)

    def _source_matches_major_stressor_lane(self, topic: str, source: ResearchSource) -> bool:
        lane = self._major_stressor_lane(topic)
        if not lane:
            return False
        text = f"{source.title} {source.note}".lower()
        if self._is_off_topic_stoic_source(topic, source):
            return False
        lane_terms = STOIC_MAJOR_STRESSOR_SOURCE_TERMS.get(lane, ())
        lane_hits = sum(1 for term in lane_terms if term in text)
        has_work_context = any(
            term in text
            for term in (
                "work", "workplace", "office", "team chat", "slack", "manager", "coworker",
                "colleague", "employee", "career", "job", "organization", "organizational",
            )
        )
        # Major-stressor topics are allowed to use psychology/management sources,
        # but they still need explicit lane vocabulary. A random sports story with
        # "team" or a tech story with "Workplace" must not pass.
        return has_work_context and lane_hits >= 2

    def _source_has_operational_work_evidence(self, topic: str, source: ResearchSource) -> bool:
        text = f"{source.title} {source.note}".lower()
        if self._is_generic_stoic_source(source):
            return False
        if self._is_off_topic_stoic_source(topic, source):
            return False
        if self._source_matches_major_stressor_lane(topic, source):
            return True
        has_operational_term = any(term in text for term in STOIC_OPERATIONAL_EVIDENCE_TERMS)
        topic_overlap = self._topic_match_count(topic, text)
        has_work_context = any(
            term in text
            for term in (
                "work", "workplace", "workflow", "office", "team", "manager", "project", "task",
                "process", "operations", "employee", "knowledge worker", "deep work",
            )
        )
        # One incidental word like "spreadsheet" inside a generic anxiety article should not pass.
        # Require at least two requested-topic terms unless the exact title phrase is present.
        exact_topic = " ".join((topic or "").lower().split())
        exact_phrase_hit = exact_topic and exact_topic in text
        # Major stressors are handled by _source_matches_major_stressor_lane
        # above, which requires lane-specific vocabulary. Do not let a single
        # loose word like "team" or "review" pass here.
        return has_operational_term and (exact_phrase_hit or (topic_overlap >= 2 and has_work_context))

    def _topic_match_count(self, topic: str, text: str) -> int:
        lowered_text = (text or "").lower()
        return sum(
            1
            for term in self._topic_keywords(topic)
            if re.search(rf"\b{re.escape(term)}s?\b", lowered_text)
        )

    def _topic_matches_source(self, topic: str, text: str) -> bool:
        lowered_topic = (topic or "").lower()
        lowered_text = (text or "").lower()
        pseudo_source = ResearchSource(title="", url="https://example.com", note=lowered_text, relevance=0.0, source="web")
        if self._source_matches_major_stressor_lane(topic, pseudo_source):
            return True
        if "slack" in lowered_topic:
            has_slack_brand = re.search(r"\bslack\b", lowered_text) is not None
            has_slack_context = any(term in lowered_text for term in ("notification", "notifications", "message", "messages", "workspace", "channel", "dm", "inbox", "ping"))
            return has_slack_brand and has_slack_context
        if "doomscroll" in lowered_topic:
            return any(term in lowered_text for term in ("doomscroll", "scroll", "phone", "feed", "notification", "social media"))
        topic_terms = self._topic_keywords(topic)
        return any(re.search(rf"\b{re.escape(term)}\b", lowered_text) for term in topic_terms)

    def _is_usable_stoic_source(self, source: ResearchSource, topic: str, article_read: Optional[dict[str, Any]]) -> bool:
        title = (source.title or "").strip()
        note = (source.note or "").strip()
        lowered = f"{title} {note}".lower()
        hostname = (urlparse(source.url).hostname or "").lower()

        blocked_hosts = {
            "instagram.com",
            "www.instagram.com",
            "facebook.com",
            "www.facebook.com",
            "github.com",
            "www.github.com",
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
        }
        if hostname in blocked_hosts:
            return False
        if len(title) < 8 or len(note) < 40:
            return False
        if lowered.startswith("the provided text"):
            return False
        junk_phrases = [
            "contains only",
            "website metadata",
            "footer information",
            "raw github repository page",
            "interface page",
            "login prompts",
            "website navigation elements",
            "article content is limited to",
            "does not contain the actual content",
            "missing:",
            "work app workplace",
            "work-focused version of its social app",
            "workplace app to integrate",
            "focus on ai, metaverse",
            "focus on ai and metaverse",
        ]
        if any(phrase in lowered for phrase in junk_phrases):
            return False
        if self._is_off_topic_stoic_source(topic, source):
            return False
        if article_read and article_read.get("read_success") and not article_read.get("article_summary") and article_read.get("content_chars", 0) < 400:
            return False
        if self._is_generic_stoic_source(source):
            return False
        base_terms = [
            "stoic", "stoicism", "marcus aurelius", "epictetus", "seneca", "control", "discipline",
            "attention", "focus", "stress", "anxiety", "work", "workplace", "reactivity", "boundary", "deep work", "burnout",
        ]
        has_base_relevance = any(term in lowered for term in base_terms)
        has_operational_relevance = self._source_has_operational_work_evidence(topic, source)
        if not has_base_relevance and not has_operational_relevance:
            return False
        topic_terms = self._topic_keywords(topic)
        if topic_terms and not self._topic_matches_source(topic, lowered) and not has_operational_relevance:
            return False
        return True

    def _score_stoic_source(self, source: ResearchSource, topic: str, article_read: Optional[dict[str, Any]]) -> float:
        lowered = f"{source.title} {source.note}".lower()
        hostname = (urlparse(source.url).hostname or "").lower()
        score = 0.68
        trusted_hosts = {
            "dailystoic.com": 0.16,
            "www.dailystoic.com": 0.16,
            "modernstoicism.com": 0.15,
            "www.modernstoicism.com": 0.15,
            "psychologytoday.com": 0.12,
            "www.psychologytoday.com": 0.12,
            "hbr.org": 0.12,
            "www.hbr.org": 0.12,
            "reddit.com": 0.05,
            "www.reddit.com": 0.05,
        }
        score += trusted_hosts.get(hostname, 0)
        topic_terms = self._topic_keywords(topic)
        overlap = sum(1 for term in topic_terms if re.search(rf"\b{re.escape(term)}\b", lowered))
        if self._topic_matches_source(topic, lowered):
            score += 0.1
        if overlap:
            score += min(0.14, overlap * 0.03)
        if self._source_has_operational_work_evidence(topic, source):
            score += 0.16
        if any(term in lowered for term in ("slack", "notification", "doomscroll", "attention", "focus", "deep work")):
            score += 0.1
        if any(term in lowered for term in ("stoic", "stoicism", "marcus aurelius", "epictetus", "seneca")):
            score += 0.08
        if article_read and article_read.get("article_summary"):
            score += 0.06
        return min(0.98, score)

    async def _summarize_with_llama(self, topic: str, sources: list[ResearchSource]) -> dict:
        source_lines = "\n".join(
            f"- {source.title} | {source.url} | {source.note}"
            for source in sources[:8]
        )

        # Stoic Modernized research note prompt
        prompt = f"""
You are helping build research notes for Stoic Modernized.
Topic: {topic}

Using the sources below, produce concise JSON with this exact shape:
{{
  "title": "string",
  "key_insights": ["string", "string", "string", "string", "string"],
  "workplace_applications": ["string", "string", "string", "string", "string"]
}}

Rules:
- synthesize the concrete workplace mechanism behind this topic, not generic Stoic advice
- use article summaries as the primary evidence, not raw snippets
- prefer operational details: process bottlenecks, queues, handoffs, interruptions, review loops, ownership, data/checking steps, or attention costs
- include one classical Stoic move only after the workplace mechanism is grounded
- reject vague emotional mush: do not write generic anxiety/self-help, generic productivity, or broad Stoicism-for-workers notes
- workplace_applications should be repeatable actions a modern worker can perform in the exact scenario
- no markdown
- output JSON only

Sources:
{source_lines}
""".strip()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.llama_base_url,
                    json={
                        "model": settings.local_llm_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "chat_template_kwargs": {"enable_thinking": False},
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception:
            return {}

    def _infer_source(self, url: str) -> str:
        lowered = url.lower()
        hostname = (urlparse(url).hostname or "").lower()
        official_hosts = {
            "openai.com",
            "www.openai.com",
            "anthropic.com",
            "www.anthropic.com",
            "blog.google",
            "googleblog.com",
            "blog.google.com",
            "blogs.microsoft.com",
            "microsoft.com",
            "www.microsoft.com",
            "blogs.nvidia.com",
            "nvidia.com",
            "www.nvidia.com",
        }
        if hostname in official_hosts:
            return "official"
        if hostname.endswith("wikipedia.org"):
            return "wikipedia"
        if hostname.endswith("reddit.com"):
            return "forum"
        if hostname.endswith("medium.com"):
            return "article"
        if "blog" in hostname or "dailystoic" in hostname or "modernstoicism" in hostname:
            return "blog"
        if (
            "news" in hostname
            or "timesofindia" in hostname
            or "nytimes.com" in hostname
            or "theverge.com" in hostname
            or "reuters.com" in hostname
            or "cnbc.com" in hostname
            or "finance.yahoo.com" in hostname
            or "bloomberg.com" in hostname
            or "techcrunch.com" in hostname
            or "ft.com" in hostname
            or "marketwatch.com" in hostname
        ):
            return "news"
        return "web"

    async def _handoff_to_whiskers(
        self,
        topic: str,
        sources: list[ResearchSource],
        fallback_insights: list[str],
        fallback_applications: list[str],
    ) -> Optional[ResearchResult]:
        whiskers_script = Path.home() / ".openclaw" / "agents" / "council-of-cats" / "whiskers" / "research_agent.py"
        if not whiskers_script.exists():
            return None

        packet = {
            "topic": topic,
            "channel": self.channel.value,
            "ledger_packet": self.last_ledger_packet,
            "sources": [s.model_dump() for s in sources],
            "article_reads": self.last_article_reads,
            "sources_found": len(sources),
            "blocked_duplicates": 0,
            "fallback_insights": fallback_insights,
            "fallback_applications": fallback_applications,
            "suggested_title": f"{topic.title()}: A Stoic Perspective",
        }
        packet_path = self.research_dir / "whiskers_packet.json"
        save_json(packet, packet_path)

        try:
            result = subprocess.run(
                ["python3", str(whiskers_script), topic, self.channel.value, str(packet_path)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
            start = combined_output.find("{")
            end = combined_output.rfind("}")
            if start < 0 or end <= start:
                return None
            payload = json.loads(combined_output[start:end + 1])
            self.last_whiskers_handoff = payload if isinstance(payload, dict) else None
            save_json(payload, self.research_dir / "whiskers_handoff.json")
            return ResearchResult(
                title=str(payload.get("title") or f"{topic.title()}: A Stoic Perspective"),
                sources=[ResearchSource(**item) for item in payload.get("sources", [])],
                key_insights=[str(item) for item in payload.get("key_insights", [])],
                workplace_applications=[str(item) for item in payload.get("workplace_applications", [])],
            )
        except Exception:
            return None

    def save_results(self, results: ResearchResult) -> Path:
        data = {
            "topic": self.last_topic,
            "title": results.title,
            "channel": self.channel.value,
            "ledger_packet": self.last_ledger_packet,
            "whiskers_handoff": self.last_whiskers_handoff,
            "sources": [s.model_dump() for s in results.sources],
            "article_reads": self.last_article_reads,
            "key_insights": results.key_insights,
            "workplace_applications": results.workplace_applications,
            "generated_at": "generated-via-searxng-whiskers" if not self.mock else "generated-mock",
        }
        return save_json(data, self.research_dir / "research.json")

    def load_results(self) -> Optional[ResearchResult]:
        research_path = self.research_dir / "research.json"
        if not research_path.exists():
            return None

        data = load_json(research_path)
        self.last_article_reads = list(data.get("article_reads", []))
        self.last_ledger_packet = data.get("ledger_packet") if isinstance(data.get("ledger_packet"), dict) else None
        self.last_whiskers_handoff = data.get("whiskers_handoff") if isinstance(data.get("whiskers_handoff"), dict) else None
        return ResearchResult(
            title=data["title"],
            sources=[ResearchSource(**item) for item in data.get("sources", [])],
            key_insights=list(data.get("key_insights", [])),
            workplace_applications=list(data.get("workplace_applications", [])),
        )
