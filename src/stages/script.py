"""Script generation stage module."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from src.config import VideoMode, settings
from src.models import Chapter, Script
from src.utils import load_json, save_json


class ScriptGenerationError(RuntimeError):
    """Raised when real local-LLM script generation fails validation or transport."""


class ScriptStage:
    """Handles script generation stage."""

    def __init__(self, job_id: str, mock: bool = False, video_mode: VideoMode = VideoMode.LONG):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.video_mode = video_mode
        self.job_dir = settings.jobs_dir / job_id
        self.script_dir = self.job_dir / "script"

    async def run(self, research_data: dict) -> Script:
        self.script_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._mock_script(research_data)
        return await self._real_script(research_data)

    async def _mock_script(self, research_data: dict) -> Script:
        topic = research_data.get("topic", "workplace stress")
        title = research_data.get("title", f"{topic.title()}: A Stoic Perspective")
        short_version = self._generate_short_narration(topic)
        narration = short_version if self.video_mode == VideoMode.SHORT else self._generate_mock_narration(topic)
        chapters = self._short_chapters() if self.video_mode == VideoMode.SHORT else self._long_chapters()

        return Script(
            title=title,
            hook=f"What if I told you that 2000 years of wisdom could help you handle {topic} better? Welcome to Stoic Modernized.",
            narration=narration,
            chapters=chapters,
            cta="If this helped you, subscribe to Stoic Modernized for more weekly videos on applying ancient wisdom to modern life. What workplace challenge should we tackle next? Let me know in the comments.",
            short_version=short_version,
            generated_at=datetime.now(UTC),
        )

    async def _real_script(self, research_data: dict) -> Script:
        topic = str(research_data.get("topic") or "workplace stress").strip()
        research_title = str(research_data.get("title") or f"{topic.title()}: A Stoic Perspective").strip()
        key_insights = self._coerce_string_list(research_data.get("key_insights"))
        workplace_applications = self._coerce_string_list(research_data.get("workplace_applications"))
        sources = self._coerce_sources(research_data.get("sources"))

        generation = await self._generate_with_local_llm(
            topic=topic,
            research_title=research_title,
            key_insights=key_insights,
            workplace_applications=workplace_applications,
            sources=sources,
        )

        parsed_payload = generation.get("parsed_payload") or {}
        repaired_payload, repairs = self._repair_generated_payload(parsed_payload)
        validation_error = self._validate_generated_payload(repaired_payload, topic=topic)
        failure_reason = generation.get("error") or validation_error
        succeeded = bool(generation.get("success")) and not bool(validation_error)

        self._write_generation_artifacts(
            raw_response=generation.get("raw_response", ""),
            parsed_payload=generation.get("parsed_payload") or {},
            final_payload=repaired_payload,
            report={
                "job_id": self.job_id,
                "video_mode": self.video_mode.value,
                "topic": topic,
                "local_llm_requested": True,
                "local_llm_success": bool(generation.get("success")),
                "used_fallback": False,
                "fallback_reason": None,
                "script_generation_succeeded": succeeded,
                "failure_reason": failure_reason,
                "llm_error": generation.get("error"),
                "repairs_applied": repairs,
                "raw_response_path": "local_llm_raw.txt",
                "parsed_payload_path": "local_llm_parsed.json",
                "final_payload_path": "script_generation_final.json",
                "generated_at": datetime.now(UTC).isoformat(),
            },
        )

        if not succeeded:
            raise ScriptGenerationError(failure_reason or "local_llm_script_generation_failed")

        return self._payload_to_script(
            payload=repaired_payload,
            topic=topic,
            research_title=research_title,
            key_insights=key_insights,
            workplace_applications=workplace_applications,
        )

    async def _generate_with_local_llm(
        self,
        *,
        topic: str,
        research_title: str,
        key_insights: list[str],
        workplace_applications: list[str],
        sources: list[dict[str, str]],
    ) -> dict[str, Any]:
        mode = self.video_mode.value
        section_blueprint = self._section_blueprint()
        source_lines = "\n".join(
            f"- {source.get('title', 'Untitled')} | {source.get('url', '')} | {source.get('note', '')}"
            for source in sources[:6]
        ) or "- No external sources available; rely on supplied research notes."
        insight_lines = "\n".join(f"- {item}" for item in key_insights) or "- No key insights provided"
        application_lines = "\n".join(f"- {item}" for item in workplace_applications) or "- No workplace applications provided"
        section_titles = self._section_blueprint()
        section_rules = "\n".join(f"- {title}" for title in section_titles)
        exact_sections_json = ",\n    ".join(
            f'{{"title": "{title}", "narration": "string"}}' for title in section_titles
        )
        short_mode_extra = ""
        if self.video_mode == VideoMode.SHORT:
            short_mode_extra = """
CRITICAL SHORT-MODE REQUIREMENTS:
- You must return exactly 4 section objects.
- The section titles must be exactly and only:
  1. Hook
  2. Stoic Principle
  3. Workplace Application
  4. CTA
- Do not invent alternate section titles.
- Do not merge sections.
- Do not omit CTA.
- Do not return 3 sections.
- The sections array must look like this exact title structure:
  [
    {"title": "Hook", "narration": "..."},
    {"title": "Stoic Principle", "narration": "..."},
    {"title": "Workplace Application", "narration": "..."},
    {"title": "CTA", "narration": "..."}
  ]
""".strip()

        prompt = f"""
You are writing a faceless YouTube script for {settings.channel_name}.

Channel voice: {settings.channel_voice}
Video mode: {mode}
Topic: {topic}
Research title: {research_title}

Key insights:
{insight_lines}

Workplace applications:
{application_lines}

Sources:
{source_lines}

Return JSON only with this exact shape:
{{
  "title": "string",
  "hook": "string",
  "cta": "string",
  "short_version": "string",
  "sections": [
    {exact_sections_json}
  ]
}}

Rules:
- make the title and narration materially specific to this topic, not generic Stoicism filler
- for Shorts, keep the title tight and natural: prefer under 12 words and do not append generic suffixes like "A Stoic Perspective"
- avoid redundant phrasing such as "How to X using Stoic Y: A Stoic Perspective"
- use practical, modern workplace language
- mention 1-2 Stoic thinkers only when relevant
- no markdown fences, no commentary, no chain-of-thought, no placeholders
- each section narration should be 2-6 sentences and flow naturally when spoken by TTS
- short_version must fit a sub-60-second Short and should still be topic-specific
- the top-level cta must match the CTA section's spoken call to action in substance
- sections must match this order and count exactly:
{section_rules}
- section titles must exactly match the required titles above
- avoid repeating the same sentence structure across sections
- do not include timestamps in the JSON
{short_mode_extra}
Before finalizing, check that the number of section objects equals {len(section_titles)}.
""".strip()

        payload = {
            "model": settings.local_script_model or settings.local_llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You write clean JSON for a YouTube automation pipeline. Respond with JSON only. Follow the exact required section schema.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": settings.local_script_temperature,
            "max_tokens": settings.local_script_max_tokens,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }

        try:
            async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
                response = await client.post(settings.local_llm_base_url, json=payload)
                response.raise_for_status()
            data = response.json()
            content = self._extract_message_content(data)
            return {
                "success": bool(content.strip()),
                "raw_response": content,
                "parsed_payload": self._parse_llm_json(content),
                "error": None if content.strip() else "local_llm_returned_empty_content",
            }
        except Exception as exc:
            return {
                "success": False,
                "raw_response": "",
                "parsed_payload": {},
                "error": f"local_llm_request_failed: {type(exc).__name__}",
            }

    def _repair_generated_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        if not isinstance(payload, dict):
            return payload, []

        repaired = dict(payload)
        repairs: list[str] = []
        sections = repaired.get("sections") if isinstance(repaired.get("sections"), list) else []
        normalized_title = self._normalize_generated_title(repaired.get("title"))
        if normalized_title and normalized_title != repaired.get("title"):
            repaired["title"] = normalized_title
            repairs.append("normalized_title")
        section_map = {
            self._clean_sentence(section.get("title")): self._clean_multiline_text(section.get("narration"))
            for section in sections
            if isinstance(section, dict)
        }

        if not self._clean_sentence(repaired.get("cta")):
            cta_text = section_map.get("CTA")
            if cta_text:
                repaired["cta"] = cta_text
                repairs.append("derived_cta_from_cta_section")
        else:
            cta_text = section_map.get("CTA")
            if cta_text:
                normalized_cta = self._normalize_cta_text(cta_text)
                repaired["cta"] = normalized_cta
                for section in sections:
                    if isinstance(section, dict) and self._clean_sentence(section.get("title")) == "CTA":
                        if self._clean_multiline_text(section.get("narration")) != normalized_cta:
                            section["narration"] = normalized_cta
                            repairs.append("aligned_cta_section_with_top_level_cta")
                        break
                if normalized_cta != cta_text:
                    repairs.append("normalized_cta_from_cta_section")

        if not self._clean_multiline_text(repaired.get("short_version")) and self.video_mode == VideoMode.SHORT:
            short_version = self._build_short_version_from_sections(section_map)
            if short_version:
                repaired["short_version"] = short_version
                repairs.append("derived_short_version_from_short_sections")

        return repaired, repairs

    def _build_short_version_from_sections(self, section_map: dict[str, str]) -> str:
        ordered_titles = ["Hook", "Stoic Principle", "Workplace Application", "CTA"]
        lines: list[str] = []
        timestamps = ["0:00-0:12", "0:12-0:30", "0:30-0:50", "0:50-0:58"]
        for ts, title in zip(timestamps, ordered_titles, strict=False):
            narration = self._clean_multiline_text(section_map.get(title))
            if not narration:
                return ""
            lines.append(f"[{ts}] {title}\n{narration}")
        return "\n\n".join(lines)

    def _write_generation_artifacts(
        self,
        *,
        raw_response: str,
        parsed_payload: dict[str, Any],
        final_payload: dict[str, Any],
        report: dict[str, Any],
    ) -> None:
        self.script_dir.mkdir(parents=True, exist_ok=True)
        (self.script_dir / "local_llm_raw.txt").write_text(raw_response or "", encoding="utf-8")
        save_json(parsed_payload, self.script_dir / "local_llm_parsed.json")
        save_json(final_payload, self.script_dir / "script_generation_final.json")
        save_json(report, self.script_dir / "script_generation_report.json")

    def _validate_generated_payload(self, payload: dict[str, Any], *, topic: str) -> Optional[str]:
        if not isinstance(payload, dict) or not payload:
            return "local_llm_payload_missing"

        required_fields = ["title", "hook", "cta", "short_version", "sections"]
        missing = [field for field in required_fields if not payload.get(field)]
        if missing:
            return f"local_llm_payload_missing_fields:{','.join(missing)}"

        sections = payload.get("sections")
        expected_titles = self._section_blueprint()
        if not isinstance(sections, list) or len(sections) != len(expected_titles):
            return "local_llm_payload_wrong_section_count"

        cleaned_sections: list[str] = []
        for index, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                return f"local_llm_section_{index}_not_an_object"
            title = self._clean_sentence(section.get("title"))
            if title != expected_titles[index - 1]:
                return f"local_llm_section_{index}_wrong_title"
            narration = self._clean_multiline_text(section.get("narration"))
            if len(narration.split()) < settings.local_script_min_section_words:
                return f"local_llm_section_{index}_too_short"
            if self._contains_placeholder_language(narration):
                return f"local_llm_section_{index}_contains_placeholder_language"
            cleaned_sections.append(narration.lower())

        combined = "\n".join(
            [
                self._clean_sentence(payload.get("title")),
                self._clean_sentence(payload.get("hook")),
                self._clean_sentence(payload.get("cta")),
                self._clean_multiline_text(payload.get("short_version")),
                *cleaned_sections,
            ]
        ).lower()
        if self._contains_placeholder_language(combined):
            return "local_llm_payload_contains_placeholder_language"
        if self._looks_like_known_generic_script(combined, topic=topic):
            return "local_llm_payload_too_generic"
        if len(set(cleaned_sections)) < max(2, len(cleaned_sections) - 2):
            return "local_llm_sections_too_repetitive"
        return None

    def _contains_placeholder_language(self, text: str) -> bool:
        normalized = text.lower()
        markers = [
            "[insert",
            "your topic",
            "placeholder",
            "lorem ipsum",
            "tbd",
            "to be added",
            "add your",
            "write here",
        ]
        return any(marker in normalized for marker in markers)

    def _looks_like_known_generic_script(self, text: str, *, topic: str) -> bool:
        generic_markers = [
            "welcome to stoic modernized. today we're exploring how ancient stoic philosophy can transform",
            "what if i told you that 2000 years of wisdom could help you handle",
            "in our fast-paced workplace, we're constantly bombarded with stress",
        ]
        if any(marker in text for marker in generic_markers):
            return True

        topic_tokens = {token for token in re.findall(r"[a-z0-9]+", topic.lower()) if len(token) > 3}
        if not topic_tokens:
            return False
        return not any(token in text for token in topic_tokens)

    def _payload_to_script(
        self,
        *,
        payload: dict[str, Any],
        topic: str,
        research_title: str,
        key_insights: list[str],
        workplace_applications: list[str],
    ) -> Script:
        _ = (topic, key_insights, workplace_applications)
        chapters = self._short_chapters() if self.video_mode == VideoMode.SHORT else self._long_chapters()
        section_titles = [chapter.title for chapter in chapters]
        sections = self._normalize_sections(payload.get("sections"), section_titles)

        title = self._normalize_generated_title(payload.get("title")) or research_title
        hook = self._clean_sentence(payload.get("hook"))
        cta = self._normalize_cta_text(payload.get("cta"))
        short_version = self._clean_multiline_text(payload.get("short_version"))
        narration = self._render_timed_narration(sections, chapters)

        return Script(
            title=title,
            hook=hook,
            narration=narration,
            chapters=chapters,
            cta=cta,
            short_version=short_version,
            generated_at=datetime.now(UTC),
        )

    def _normalize_sections(self, raw_sections: Any, section_titles: list[str]) -> list[dict[str, str]]:
        items = raw_sections if isinstance(raw_sections, list) else []
        normalized: list[dict[str, str]] = []

        for index, title in enumerate(section_titles):
            source = items[index] if index < len(items) and isinstance(items[index], dict) else {}
            narration = self._clean_multiline_text(source.get("narration"))
            normalized.append(
                {
                    "title": self._clean_sentence(source.get("title")) or title,
                    "narration": narration,
                }
            )
        return normalized

    def _render_timed_narration(self, sections: list[dict[str, str]], chapters: list[Chapter]) -> str:
        blocks: list[str] = []
        for index, section in enumerate(sections):
            chapter = chapters[index]
            next_timestamp = chapters[index + 1].timestamp if index + 1 < len(chapters) else self._chapter_end_time(index)
            label = self._format_timerange(chapter.timestamp, next_timestamp)
            narration = section.get("narration") or f"A practical Stoic reflection on {section['title'].lower()}."
            blocks.append(f"[{label}] {section['title']}\n{narration}")
        return "\n\n".join(blocks)

    def _chapter_end_time(self, index: int) -> float:
        if self.video_mode == VideoMode.SHORT:
            ends = [12.0, 30.0, 50.0, 58.0]
            return ends[min(index, len(ends) - 1)]
        ends = [30.0, 90.0, 180.0, 270.0, 360.0, 450.0, 510.0, 540.0]
        return ends[min(index, len(ends) - 1)]

    def _format_timerange(self, start: float, end: float) -> str:
        return f"{self._format_seconds(start)}-{self._format_seconds(end)}"

    def _format_seconds(self, value: float) -> str:
        total_seconds = max(0, int(round(value)))
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    def _section_blueprint(self) -> list[str]:
        if self.video_mode == VideoMode.SHORT:
            return [chapter.title for chapter in self._short_chapters()]
        return [chapter.title for chapter in self._long_chapters()]

    def _short_chapters(self) -> list[Chapter]:
        return [
            Chapter(title="Hook", timestamp=0.0),
            Chapter(title="Stoic Principle", timestamp=12.0),
            Chapter(title="Workplace Application", timestamp=30.0),
            Chapter(title="CTA", timestamp=50.0),
        ]

    def _long_chapters(self) -> list[Chapter]:
        return [
            Chapter(title="Introduction", timestamp=0.0),
            Chapter(title="The Problem", timestamp=30.0),
            Chapter(title="Marcus Aurelius on Control", timestamp=90.0),
            Chapter(title="Seneca on Time Management", timestamp=180.0),
            Chapter(title="Epictetus on Expectations", timestamp=270.0),
            Chapter(title="Practical Techniques", timestamp=360.0),
            Chapter(title="Conclusion", timestamp=450.0),
            Chapter(title="Call to Action", timestamp=510.0),
        ]

    def _generate_short_narration(self, topic: str) -> str:
        return f"""[0:00-0:12] Hook
Work stress feels overwhelming when you confuse what happened with how you respond to it.

[0:12-0:30] Stoic Principle
Marcus Aurelius reminds us that you control your mind, not outside events. That means the meeting, the email, and the deadline are real — but your reaction is still yours.

[0:30-0:50] Workplace Application
Before you answer the next stressful message, pause. Breathe. Ask what is actually under your control right now. That single beat is where Stoicism becomes useful at work.

[0:50-0:58] CTA
Follow Stoic Modernized for practical Stoic strategies for {topic}."""

    def _generate_mock_narration(self, topic: str) -> str:
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

    def _coerce_string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _coerce_sources(self, value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, str]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(
                    {
                        "title": str(item.get("title") or "").strip(),
                        "url": str(item.get("url") or "").strip(),
                        "note": str(item.get("note") or "").strip(),
                    }
                )
        return normalized

    def _extract_message_content(self, data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text") or ""))
            return "\n".join(part for part in text_parts if part)
        return ""

    def _parse_llm_json(self, content: str) -> dict[str, Any]:
        cleaned = (content or "").strip()
        if not cleaned:
            return {}

        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned).strip()

        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return {}

        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _clean_sentence(self, value: Any) -> str:
        text = self._clean_multiline_text(value)
        return text.replace("\n", " ").strip()

    def _clean_multiline_text(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        text = value.replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _normalize_generated_title(self, value: Any) -> str:
        title = self._clean_sentence(value)
        if not title:
            return ""

        title = re.sub(r"\s*\|\s*Stoic Modernized\s*$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*[-:]\s*A Stoic Perspective\s*$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*[-:]\s*Stoic Perspective\s*$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s+", " ", title).strip(" -:")

        if self.video_mode == VideoMode.SHORT:
            title = re.sub(r"^How To\b", "How to", title)
            title = re.sub(r"\bUsing Stoic Control\b", "with Stoic Control", title, flags=re.IGNORECASE)
            words = title.split()
            if len(words) > 12:
                trimmed = [
                    word
                    for word in words
                    if word.lower() not in {"stoic", "stoicism", "perspective", "modernized"}
                ]
                title = " ".join((trimmed or words)[:12]).strip()
        return title

    def _normalize_cta_text(self, value: Any) -> str:
        text = self._clean_sentence(value)
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text).strip()
        if not re.search(r"[.!?]$", text):
            text += "."
        return text

    def save_script(self, script: Script) -> Path:
        data = script.model_dump(mode="json")
        return save_json(data, self.script_dir / "script.json")

    def load_script(self) -> Optional[Script]:
        script_path = self.script_dir / "script.json"
        if not script_path.exists():
            return None

        data = load_json(script_path)
        return Script(**data)
