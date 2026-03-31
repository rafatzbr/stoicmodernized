"""Script generation stage module."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import settings
from src.models import Chapter, Script
from src.utils import save_json


class ScriptStage:
    """Handles script generation stage."""

    def __init__(self, job_id: str, mock: bool = False):
        """Initialize script stage.

        Args:
            job_id: Unique job identifier
            mock: If True, use mock data
        """
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.job_dir = settings.jobs_dir / job_id
        self.script_dir = self.job_dir / "script"

    async def run(self, research_data: dict) -> Script:
        """Generate a script based on research data.

        Args:
            research_data: Dictionary containing research results

        Returns:
            Script object with full script content
        """
        self.script_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._mock_script(research_data)
        else:
            return await self._real_script(research_data)

    async def _mock_script(self, research_data: dict) -> Script:
        """Generate mock script data."""
        topic = research_data.get("topic", "workplace stress")
        title = research_data.get("title", f"{topic.title()}: A Stoic Perspective")

        return Script(
            title=title,
            hook=f"What if I told you that 2000 years of wisdom could help you handle {topic} better? Welcome to Stoic Modernized.",
            narration=self._generate_mock_narration(topic),
            chapters=[
                Chapter(title="Introduction", timestamp=0.0),
                Chapter(title="The Problem", timestamp=30.0),
                Chapter(title="Marcus Aurelius on Control", timestamp=90.0),
                Chapter(title="Seneca on Time Management", timestamp=180.0),
                Chapter(title="Epictetus on Expectations", timestamp=270.0),
                Chapter(title="Practical Techniques", timestamp=360.0),
                Chapter(title="Conclusion", timestamp=450.0),
                Chapter(title="Call to Action", timestamp=510.0),
            ],
            cta="If this helped you, subscribe to Stoic Modernized for more weekly videos on applying ancient wisdom to modern life. What workplace challenge should we tackle next? Let me know in the comments.",
            short_version=f"Ancient Stoics had a secret for handling {topic}. Marcus Aurelius taught that you control your reaction, not events. Seneca said we make life short by wasting time. Epictetus said obstacles are training opportunities. Next time you're stressed, pause for three breaths before responding. That's where your freedom lives. Subscribe to Stoic Modernized for more weekly wisdom.",
            generated_at=datetime.utcnow(),
        )

    async def _real_script(self, research_data: dict) -> Script:
        """Generate real script using LLM.

        TODO: Implement integration with LLM APIs (OpenAI, Anthropic, etc.)
        """
        raise NotImplementedError("Real script generation requires LLM API integration")

    def _generate_mock_narration(self, topic: str) -> str:
        """Generate mock narration text for testing."""
        return f"""[0:00-0:30] Introduction
Welcome to Stoic Modernized. Today we're exploring how ancient Stoic philosophy can transform the way you handle {topic} in your modern work life.

[0:30-1:30] The Problem
In our fast-paced workplace, we're constantly bombarded with stress, deadlines, and difficult colleagues. We feel like we've lost control. But what if the solution has been right in front of us all along?

[1:30-3:00] Marcus Aurelius on Control
Marcus Aurelius, Roman Emperor and Stoic philosopher, wrote in his Meditations: "You have power over your mind - not outside events. Realize this, and you will find strength."

Think about your last stressful meeting. Was it the meeting itself that upset you? Or was it your reaction to it? This is the core Stoic insight that can change everything.

[3:00-4:30] Seneca on Time Management
Seneca wrote extensively about time as our most precious resource. "We are not given a short life but we make it short."

In the workplace, this means being intentional about how we spend our hours. Are you responding to every email immediately? Are you attending meetings that could have been emails?

[4:30-6:00] Epictetus on Expectations
Epictetus taught: "He who desires to succeed must accept and love the obstacles that come his way."

The next time a project fails or a client is unreasonable, instead of frustration, see it as training. Each difficulty is an opportunity to practice your Stoic discipline.

[6:00-7:30] Practical Techniques
Here are three Stoic practices for the workplace:

First, the morning preparation. Before your workday begins, visualize potential challenges. Not to worry about them, but to prepare your mind to face them with calm.

Second, the evening review. Before sleep, reflect on your day. Where did you react well? Where could you have been more Stoic? This isn't self-criticism - it's self-improvement.

Third, the pause. When something triggers you at work, take three deep breaths before responding. In that space between stimulus and response lies your freedom.

[7:30-8:30] Conclusion
Stoicism isn't about suppressing emotions or becoming passive. It's about understanding what you can control and acting wisely within those bounds.

The next time you face {topic}, remember: you have more power than you think.

[8:30-9:00] Call to Action
If this helped you, subscribe to Stoic Modernized for more weekly videos on applying ancient wisdom to modern life. What workplace challenge should we tackle next? Let me know in the comments."""

    def save_script(self, script: Script) -> Path:
        """Save script to JSON file.

        Args:
            script: Script object to save

        Returns:
            Path to the saved JSON file
        """
        data = script.model_dump(mode="json")
        return save_json(data, self.script_dir / "script.json")

    def load_script(self) -> Optional[Script]:
        """Load script from JSON file.

        Returns:
            Script object if found, None otherwise
        """
        script_path = self.script_dir / "script.json"
        if not script_path.exists():
            return None

        data = save_json.__globals__["load_json"](script_path)
        return Script(**data)
