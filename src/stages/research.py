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
        """Initialize research stage.

        Args:
            job_id: Unique job identifier
            mock: If True, use mock data instead of real API calls
        """
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.job_dir = settings.jobs_dir / job_id
        self.research_dir = self.job_dir / "research"

    async def run(self, topic: str) -> ResearchResult:
        """Run research on the given topic.

        Args:
            topic: The topic to research

        Returns:
            ResearchResult with sources and insights
        """
        # Ensure research directory exists
        self.research_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._mock_research(topic)
        else:
            return await self._real_research(topic)

    async def _mock_research(self, topic: str) -> ResearchResult:
        """Generate mock research data."""
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
        """Perform real research using web search.

        TODO: Implement integration with search APIs (Google Custom Search, Bing, etc.)
        """
        raise NotImplementedError("Real research implementation requires API keys")

    def save_results(self, results: ResearchResult) -> Path:
        """Save research results to JSON file.

        Args:
            results: Research results to save

        Returns:
            Path to the saved JSON file
        """
        data = {
            "topic": results.topic,
            "title": results.title,
            "sources": [s.model_dump() for s in results.sources],
            "key_insights": results.key_insights,
            "workplace_applications": results.workplace_applications,
            "generated_at": "TODO: Add timestamp",
        }
        return save_json(data, self.research_dir / "research.json")

    def load_results(self) -> Optional[ResearchResult]:
        """Load research results from JSON file.

        Returns:
            ResearchResult if found, None otherwise
        """
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
