"""Research stage module for gathering sources and insights."""

from pathlib import Path
from typing import Optional

import httpx

from src.config import settings
from src.models import ResearchResult, ResearchSource
from src.utils import load_json, save_json


class ResearchStage:
    """Handles the research stage of the pipeline."""

    def __init__(self, job_id: str, mock: bool = False):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.job_dir = settings.jobs_dir / job_id
        self.research_dir = self.job_dir / "research"
        self.last_topic: Optional[str] = None
        self.searxng_base_url = "http://192.168.0.12:8080"
        self.llama_base_url = "http://localhost:8080/v1/chat/completions"

    async def run(self, topic: str) -> ResearchResult:
        self.last_topic = topic
        self.research_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._mock_research(topic)
        return await self._real_research(topic)

    async def _mock_research(self, topic: str) -> ResearchResult:
        return ResearchResult(
            title=f"{topic.title()}: A Stoic Perspective",
            sources=[
                ResearchSource(
                    title="Meditations - Marcus Aurelius",
                    url="https://en.wikipedia.org/wiki/Meditations_(Marcus_Aurelius)",
                    note="Primary source on Stoic practical philosophy",
                    relevance=0.95,
                    source="wikipedia",
                ),
                ResearchSource(
                    title="Letters from a Stoic - Seneca",
                    url="https://en.wikipedia.org/wiki/Letters_from_a_Stoic",
                    note="Practical advice on managing emotions and work",
                    relevance=0.90,
                    source="wikipedia",
                ),
                ResearchSource(
                    title="The Enchiridion - Epictetus",
                    url="https://en.wikipedia.org/wiki/Enchiridion_(philosophy)",
                    note="Handbook of Stoic principles for daily life",
                    relevance=0.85,
                    source="wikipedia",
                ),
                ResearchSource(
                    title="Modern Stoicism Blog",
                    url="https://www.modernstoicism.com",
                    note="Contemporary applications of Stoic philosophy",
                    relevance=0.80,
                    source="blog",
                ),
            ],
            key_insights=[
                f"Stoicism teaches that we control our reactions to {topic}, not the events themselves.",
                "Ancient Stoics practiced negative visualization to prepare for workplace challenges.",
                "The dichotomy of control applies directly to modern management situations.",
                f"Applying Stoic principles to {topic} can reduce stress and improve decision-making.",
            ],
            workplace_applications=[
                "Use the morning preparation technique before difficult meetings.",
                "Apply the view from above to reduce stress about deadlines.",
                "Practice amor fati when projects don't go as planned.",
                "Distinguish between what you control (effort, attitude) and what you don't (outcomes, others' opinions).",
            ],
        )

    async def _real_research(self, topic: str) -> ResearchResult:
        sources = await self._search_searxng(topic)
        if not sources:
            return await self._mock_research(topic)

        fallback_insights = [
            f"Search results for '{topic}' emphasize practical emotional regulation and locus of control.",
            "Multiple sources connect Stoic practice to stress management, resilience, and better workplace judgment.",
            "Modern articles frequently translate classical Stoic ideas into office conflict, deadlines, and burnout prevention.",
            f"The strongest research angle for '{topic}' is practical application rather than abstract philosophy.",
        ]
        fallback_applications = [
            "Use the dichotomy of control to separate effort from outcomes at work.",
            "Frame stressful meetings as opportunities to practice composure and clear judgment.",
            "Translate philosophical ideas into concrete routines like pause-before-response and evening review.",
            "Turn obstacles into training reps for patience, perspective, and deliberate action.",
        ]

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
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{self.searxng_base_url}/search",
                params={"q": f"stoicism {topic}", "format": "json"},
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        sources: list[ResearchSource] = []
        for index, item in enumerate(data.get("results", [])[:6]):
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            note = (item.get("content") or item.get("snippet") or "").strip()
            if not title or not url:
                continue
            relevance = max(0.55, 0.95 - (index * 0.07))
            sources.append(
                ResearchSource(
                    title=title,
                    url=url,
                    note=note,
                    relevance=round(relevance, 2),
                    source=self._infer_source(url),
                )
            )
        return sources

    async def _summarize_with_llama(
        self, topic: str, sources: list[ResearchSource]
    ) -> dict:
        source_lines = "\n".join(
            f"- {source.title} | {source.url} | {source.note}"
            for source in sources[:6]
        )
        prompt = f"""
You are helping build research notes for a faceless YouTube automation pipeline.
Topic: {topic}

Using the sources below, produce concise JSON with this exact shape:
{{
  "title": "string",
  "key_insights": ["string", "string", "string", "string"],
  "workplace_applications": ["string", "string", "string", "string"]
}}

Rules:
- keep tone calm, practical, concise, modern
- translate Stoic philosophy into workplace application
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
                        "model": "local",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                import json

                return json.loads(content)
        except Exception:
            return {}

    def _infer_source(self, url: str) -> str:
        lowered = url.lower()
        if "wikipedia.org" in lowered:
            return "wikipedia"
        if "reddit.com" in lowered:
            return "forum"
        if "medium.com" in lowered:
            return "article"
        if "blog" in lowered or "dailystoic" in lowered or "stoic" in lowered:
            return "blog"
        return "web"

    def save_results(self, results: ResearchResult) -> Path:
        data = {
            "topic": self.last_topic,
            "title": results.title,
            "sources": [s.model_dump() for s in results.sources],
            "key_insights": results.key_insights,
            "workplace_applications": results.workplace_applications,
            "generated_at": "generated-via-searxng-llama" if not self.mock else "generated-mock",
        }
        return save_json(data, self.research_dir / "research.json")

    def load_results(self) -> Optional[ResearchResult]:
        research_path = self.research_dir / "research.json"
        if not research_path.exists():
            return None

        data = load_json(research_path)
        return ResearchResult(
            title=data["title"],
            sources=[ResearchSource(**s) for s in data.get("sources", [])],
            key_insights=data.get("key_insights", []),
            workplace_applications=data.get("workplace_applications", []),
        )
