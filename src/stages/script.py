"""Script generation stage module."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from src.config import Channel, VideoMode, settings
from src.ledger_strategy import LedgerStrategyManager
from src.models import Chapter, Script
from src.stages.upload import BLOCKED_TOPIC_KEYWORDS
from src.utils import load_json, save_json


class ScriptGenerationError(RuntimeError):
    """Raised when real local-LLM script generation fails validation or transport."""


class ScriptStage:
    """Handles script generation stage."""

    def __init__(
        self,
        job_id: str,
        mock: bool = False,
        video_mode: VideoMode = VideoMode.LONG,
        channel: Channel = settings.default_channel,
    ):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.video_mode = video_mode
        self.channel = channel
        self.job_dir = settings.jobs_dir / job_id
        self.script_dir = self.job_dir / "script"
        self.workspace_artifacts_dir = Path.home() / ".openclaw" / "workspace" / "artifacts"
        self.strategy_manager = LedgerStrategyManager()
        self.last_steering_chain: dict[str, Any] | None = None

    def _progress(self, message: str) -> None:
        """Emit unbuffered stage logs so long council runs stay visible."""
        print(message, flush=True)

    def validate_script_quality(self, script: Script, research_result: dict = None) -> dict[str, Any]:
        """Validate script quality before proceeding."""
        issues = []
        metrics = {
            "title_length": len(script.title or ""),
            "hook_length": len(script.hook or ""),
            "narration_length": len(script.narration or ""),
            "item_count": len(script.chapters or []),
            "cta_length": len(script.cta or ""),
            "has_hook": bool(script.hook and script.hook.strip()),
            "has_cta": bool(script.cta and script.cta.strip()),
            "has_title_screen": False,
            "has_title_announcement": False,
            "story_count": 0,
            "distinct_story_titles": 0,
        }

        if not script.title or len(script.title) < 10:
            issues.append("Title too short or missing")

        min_items = 3
        if not script.narration or len(script.narration.strip()) < 100:
            issues.append("Narration too short or missing")

        if len(script.chapters or []) < min_items:
            issues.append(f"Insufficient items: {len(script.chapters or [])} < {min_items}")

        if not script.cta or len(script.cta.strip()) < 10:
            issues.append("CTA too short or missing")

        if script.narration:
            malformed_patterns = [
                r"\b(\w+)\s+\w+\.\s+\w+\s+\w+\.\s+\1\b",
                r"\.{2,}",
                r"\b[A-Z]{5,}\b",
            ]
            for pattern in malformed_patterns:
                if re.search(pattern, script.narration):
                    issues.append(f"Potential malformed text detected (pattern: {pattern})")
                    break

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "metrics": metrics,
            "min_requirements": {
                "title_length": 10,
                "hook_length": 0,
                "narration_length": 100,
                "item_count": min_items,
                "cta_length": 10,
                "transitions": 0,
            },
        }

    async def run(self, research_data: dict) -> Script:
        self.script_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._mock_script(research_data)
        return await self._real_script(research_data)

    async def _load_fallback_script(self, topic: str) -> Script:
        """Load fallback script if generation fails."""
        self._progress(f"[ScriptStage] Attempting fallback script for topic: {topic}")

        # Find most recent successful script job
        import os
        from datetime import datetime, timezone

        jobs_dir = self.job_dir.parent
        if not jobs_dir.exists():
            raise RuntimeError(f"Jobs directory not found: {jobs_dir}")

        recent_jobs = []
        for job_id in os.listdir(jobs_dir):
            if job_id == self.job_id:
                continue
            job_path = jobs_dir / job_id
            if job_path.is_dir():
                script_path = job_path / "script" / "script.json"
                if script_path.exists():
                    try:
                        import json
                        with open(script_path) as f:
                            data = json.load(f)
                        recent_jobs.append({
                            "job_id": job_id,
                            "data": data,
                            "path": script_path,
                        })
                    except Exception:
                        continue

        # Sort by recency (most recent first)
        recent_jobs.sort(key=lambda x: x["path"].stat().st_mtime, reverse=True)

        for candidate in recent_jobs:
            fallback_data = candidate["data"]
            if str(fallback_data.get("channel") or self.channel.value) != self.channel.value:
                continue

            chapters = []
            for ch in fallback_data.get("chapters", []):
                chapters.append(Chapter(
                    title=ch.get("title", "Untitled"),
                    timestamp=ch.get("timestamp", 0.0),
                ))

            from datetime import UTC
            fallback_script = Script(
                title=fallback_data.get("title", topic),
                hook=fallback_data.get("hook", ""),
                narration=fallback_data.get("narration", ""),
                chapters=chapters,
                cta=fallback_data.get("cta", ""),
                short_version=fallback_data.get("short_version", ""),
                generated_at=datetime.now(UTC),
            )

            validation = self.validate_script_quality(fallback_script)
            if validation["passed"]:
                self._progress(f"[ScriptStage] Using fallback from job: {candidate['job_id']}")
                return fallback_script

        # Ultimate fallback: generate minimal script
        fallback_hook = f"What if I told you that 2000 years of wisdom could help you handle {topic} better? Welcome to Stoic Modernized."
        fallback_title = f"{topic}: A Stoic Perspective" if topic else "Stoic Wisdom: A Modern Perspective"
        fallback_narration = f"{topic}.\n\n"
        chapters = []
        timestamp = 0.0

        for i in range(5):
            chapters.append(Chapter(
                title=f"Topic {i+1}",
                timestamp=timestamp,
            ))
            timestamp += 6.0

        fallback_cta = "Subscribe to Stoic Modernized for more Stoic wisdom."

        return Script(
            title=fallback_title,
            hook=fallback_hook,
            narration=fallback_narration,
            chapters=chapters,
            cta=fallback_cta,
            short_version=fallback_narration[:200],
            generated_at=datetime.now(UTC),
        )

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
        """Generate real script using the council of cats workflow."""
        topic = str(research_data.get("topic") or "workplace stress").strip()
        research_title = str(research_data.get("title") or f"{topic.title()}: Key Insights").strip()
        sources = self._coerce_sources(research_data.get("sources"))
        key_insights = self._coerce_string_list(research_data.get("key_insights"))
        workplace_applications = self._coerce_string_list(research_data.get("workplace_applications"))
        current_job_packet = self.strategy_manager.load_job_packet(self.job_id)
        embedded_packet = research_data.get("ledger_packet") if isinstance(research_data.get("ledger_packet"), dict) else None
        ledger_packet = current_job_packet or embedded_packet
        whiskers_handoff = research_data.get("whiskers_handoff") if isinstance(research_data.get("whiskers_handoff"), dict) else None
        retry_feedback: str | None = None
        last_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                return await self._run_council_workflow(
                    topic=topic,
                    research_title=research_title,
                    key_insights=key_insights,
                    workplace_applications=workplace_applications,
                    sources=sources,
                    ledger_packet=ledger_packet,
                    whiskers_handoff=whiskers_handoff,
                    retry_feedback=retry_feedback,
                )
            except ScriptGenerationError as e:
                last_error = e
                self._progress(f"[ScriptStage] Script generation attempt {attempt} failed: {e}")
                if attempt >= 3:
                    raise
                retry_feedback = self._build_retry_feedback(topic, e)
            except Exception as e:
                self._progress(f"[ScriptStage] LLM call failed: {e}")
                raise ScriptGenerationError(f"Script generation failed: {e}")

        raise ScriptGenerationError(f"Script generation failed: {last_error}")

    async def _run_council_workflow(
        self,
        topic: str,
        research_title: str,
        key_insights: list[str],
        workplace_applications: list[str],
        sources: list[str],
        ledger_packet: dict[str, Any] | None = None,
        whiskers_handoff: dict[str, Any] | None = None,
        retry_feedback: str | None = None,
    ) -> Script:
        """Run Stoic script generation through the council of cats."""
        research_packet = {
            "topic": topic,
            "research_title": research_title,
            "video_mode": self.video_mode.value,
            "channel": self.channel.value,
            "key_insights": key_insights,
            "workplace_applications": workplace_applications,
            "sources": sources,
            "ledger_packet": ledger_packet or self.strategy_manager.load_job_packet(self.job_id),
            "whiskers_handoff": whiskers_handoff,
            "retry_feedback": retry_feedback,
        }

        self._progress("[ScriptStage] Council step: Whiskers brief")
        whiskers_brief = whiskers_handoff or await self._call_council_agent(
            agent_name="Whiskers",
            role_prompt=(
                "You are Whiskers, the Stoic Modernized researcher. Distill the research into a tight brief for the writing cats. "
                "Focus on one concrete modern work scenario, one Stoic principle, and the strongest evidence-backed claims."
            ),
            task_prompt=self._build_whiskers_prompt(research_packet),
            max_tokens=900,
        )

        self._progress("[ScriptStage] Council step: Ledger strategy")
        ledger_strategy = await self._call_council_agent(
            agent_name="Ledger",
            role_prompt=(
                "You are Ledger, the Stoic Modernized analytics and growth strategist. Read the latest channel evidence, "
                "separate reach from conversion, and translate it into concrete packaging guidance for this specific video."
            ),
            task_prompt=self._build_ledger_prompt(research_packet, whiskers_brief),
            max_tokens=700,
        )

        self._progress("[ScriptStage] Council step: Scratch draft")
        scratch_draft = await self._call_council_agent(
            agent_name="Scratch",
            role_prompt=(
                "You are Scratch, the Stoic Modernized scriptwriter. Write the first script draft from the Whiskers brief. "
                "You write clean, specific, practical narration with exact scene-ready beats."
            ),
            task_prompt=self._build_scratch_prompt(research_packet, whiskers_brief, ledger_strategy),
            max_tokens=settings.local_script_max_tokens,
        )

        self._progress("[ScriptStage] Council step: Tweezers edit")
        tweezers_edit = await self._call_council_agent(
            agent_name="Tweezers",
            role_prompt=(
                "You are Tweezers, the Stoic Modernized script editor. Improve pacing, specificity, transitions, and factual grounding. "
                "Keep scene beats coherent and remove fluff."
            ),
            task_prompt=self._build_tweezers_prompt(research_packet, scratch_draft, ledger_strategy),
            max_tokens=settings.local_script_max_tokens,
        )

        self._progress("[ScriptStage] Council step: Paw hook")
        paw_hook = await self._call_council_agent(
            agent_name="Paw",
            role_prompt=(
                "You are Paw, the hook editor. Generate the sharpest non-clickbait title and hook for this Stoic Modernized video."
            ),
            task_prompt=self._build_paw_prompt(research_packet, tweezers_edit, ledger_strategy),
            max_tokens=400,
        )

        self._progress("[ScriptStage] Council step: Speak polish")
        speak_polish = await self._call_council_agent(
            agent_name="Speak",
            role_prompt=(
                "You are Speak, the TTS optimizer. Rewrite only as needed so the script sounds natural aloud, preserves scene-sized thought units, and keeps the same claims."
            ),
            task_prompt=self._build_speak_prompt(research_packet, tweezers_edit, paw_hook, ledger_strategy),
            max_tokens=settings.local_script_max_tokens,
        )
        speak_polish = self._normalize_council_script_payload(speak_polish)

        self._progress("[ScriptStage] Council step: Mittens review")
        mittens_review = await self._call_council_agent(
            agent_name="Mittens",
            role_prompt=(
                "You are Mittens, the final script reviewer. Check for malformed text, weak claims, generic sludge, and pacing drift. "
                "Approve only if this is ready for scene planning."
            ),
            task_prompt=self._build_mittens_prompt(research_packet, speak_polish, ledger_strategy),
            max_tokens=900,
        )
        if isinstance(mittens_review.get("script"), dict):
            mittens_review["script"] = self._normalize_council_script_payload(mittens_review["script"])

        self._progress("[ScriptStage] Council step: Mr. Jim review")
        mr_jim_review = await self._call_council_agent(
            agent_name="Mr. Jim Business",
            role_prompt=(
                "You are Mr. Jim Business, chief of staff for Stoic Modernized. Verify the script matches channel voice, video mode, and scene-planning needs. "
                "Reject if it is not operationally ready."
            ),
            task_prompt=self._build_mr_jim_prompt(research_packet, mittens_review, ledger_strategy),
            max_tokens=900,
        )
        if isinstance(mr_jim_review.get("script"), dict):
            mr_jim_review["script"] = self._normalize_council_script_payload(mr_jim_review["script"])

        remediation_review = None
        if not bool(mr_jim_review.get("approved", False)):
            self._progress("[ScriptStage] Council step: Mr. Jim revision")
            remediation_review = await self._call_council_agent(
                agent_name="Mr. Jim Business",
                role_prompt=(
                    "You are Mr. Jim Business, chief of staff for Stoic Modernized. Repair the script using the review findings so it is operationally ready for scene planning."
                ),
                task_prompt=self._build_mr_jim_revision_prompt(research_packet, mittens_review, mr_jim_review, ledger_strategy),
                max_tokens=settings.local_script_max_tokens,
            )
            if isinstance(remediation_review.get("script"), dict):
                remediation_review["script"] = self._normalize_council_script_payload(remediation_review["script"])

        artifact = {
            "generated_at": datetime.now(UTC).isoformat(),
            "job_id": self.job_id,
            "channel": self.channel.value,
            "video_mode": self.video_mode.value,
            "research_packet": research_packet,
            "steering_chain": {
                "ledger_packet": research_packet.get("ledger_packet"),
                "whiskers_handoff": research_packet.get("whiskers_handoff"),
                "whiskers_brief": whiskers_brief,
                "ledger_strategy": ledger_strategy,
            },
            "whiskers": whiskers_brief,
            "ledger": ledger_strategy,
            "scratch": scratch_draft,
            "tweezers": tweezers_edit,
            "paw": paw_hook,
            "speak": speak_polish,
            "mittens": mittens_review,
            "mr_jim_business": mr_jim_review,
        }
        if remediation_review is not None:
            artifact["mr_jim_revision"] = remediation_review
        self._save_council_artifact(artifact)
        self.last_steering_chain = artifact.get("steering_chain") if isinstance(artifact.get("steering_chain"), dict) else None

        final_review = remediation_review or mr_jim_review
        approved = bool(final_review.get("approved", False))
        final_script_payload = final_review.get("script") or mr_jim_review.get("script") or mittens_review.get("script") or speak_polish
        if not approved:
            issues = final_review.get("issues") or mr_jim_review.get("issues") or mittens_review.get("issues") or ["Council review rejected script"]
            raise ScriptGenerationError("Council rejected script: " + "; ".join(str(issue) for issue in issues))

        return self._parse_script_response(self._normalize_council_script_payload(final_script_payload), topic)

    def _normalize_council_script_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize council-produced script JSON into stage-safe structure."""
        normalized = dict(payload or {})
        expected_timestamps = [0, 12, 30, 50] if self.video_mode == VideoMode.SHORT else [0, 8, 16, 24, 32]
        chapter_count = len(expected_timestamps)
        chapters = normalized.get("chapters") if isinstance(normalized.get("chapters"), list) else []
        fixed_chapters: list[dict[str, Any]] = []
        for idx in range(chapter_count):
            item = chapters[idx] if idx < len(chapters) and isinstance(chapters[idx], dict) else {}
            fixed_chapters.append({
                "title": str(item.get("title") or f"Topic {idx + 1}"),
                "timestamp": expected_timestamps[idx],
            })
        normalized["chapters"] = fixed_chapters
        if self.video_mode == VideoMode.SHORT:
            normalized["chapters"] = [
                {"title": "Hook", "timestamp": 0},
                {"title": "Stoic Principle", "timestamp": 12},
                {"title": "Workplace Application", "timestamp": 30},
                {"title": "CTA", "timestamp": 50},
            ]
            hook = str(normalized.get("hook") or "").strip()
            narration = str(normalized.get("narration") or "").strip()
            cta = str(normalized.get("cta") or "").strip()
            narration = self._normalize_short_narration_blocks(hook, narration, cta)
            normalized["narration"] = narration
            normalized["short_version"] = narration
        return normalized

    async def _call_council_agent(
        self,
        agent_name: str,
        role_prompt: str,
        task_prompt: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Call local LLM as a specific council cat and parse JSON output."""
        system_prompt = (
            f"You are {agent_name} from Rafael's Council of Cats. {role_prompt} "
            "Return valid JSON only. No markdown. No commentary outside JSON."
        )
        prompts = [
            task_prompt,
            task_prompt
            + "\n\nRETRY: Your last response was malformed or truncated. Return the same JSON schema, but shorter."
            + "\n- Keep every string concise."
            + "\n- Keep list items short fragments, not full paragraphs."
            + "\n- Close all quotes and braces."
            + "\n- Output one valid JSON object only.",
        ]
        last_error: ScriptGenerationError | None = None
        for prompt in prompts:
            try:
                result = await self._call_local_llm(
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    max_tokens=max_tokens,
                )
                if not isinstance(result, dict):
                    raise ScriptGenerationError(f"{agent_name} returned non-JSON content")
                return result
            except ScriptGenerationError as exc:
                last_error = exc
        raise last_error or ScriptGenerationError(f"{agent_name} failed to return valid JSON")

    async def _call_local_llm(self, system_prompt: str, user_prompt: str, max_tokens: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
            response = await client.post(
                settings.local_llm_base_url,
                json={
                    "model": settings.local_script_model or settings.local_llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": settings.local_script_temperature,
                    "max_tokens": max_tokens,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            )
            response.raise_for_status()
            result = response.json()
        choice = (result.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = ""
        for candidate in (message.get("content"), choice.get("text"), result.get("content")):
            if isinstance(candidate, str) and candidate.strip():
                content = candidate.strip()
                break
        if not content:
            raise ScriptGenerationError(f"Empty LLM content payload: {result}")
        if "```json" in content:
            content = content.split("```json", 1)[1].split("```", 1)[0].strip()
        elif content.startswith("```"):
            content = content.split("```", 1)[1].rsplit("```", 1)[0].strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            salvaged = self._salvage_council_payload(content)
            if salvaged is not None:
                return salvaged
            raise ScriptGenerationError(f"Failed to parse council JSON: content={content[:500]}")

    def _build_whiskers_prompt(self, research_packet: dict[str, Any]) -> str:
        return f"""
Research packet:
{json.dumps(research_packet, ensure_ascii=False, indent=2)}

Return JSON only with this exact shape:
{{
  "topic_angle": "string",
  "viewer_problem": "string",
  "stoic_move": "string",
  "work_scenario": "string",
  "evidence_points": ["string", "string", "string"],
  "scene_beats": ["string", "string", "string", "string"],
  "red_flags": ["string"]
}}

Rules:
- Prefer the supplied `whiskers_handoff` when it exists; refine it only if needed.
- Prefer the per-job `ledger_packet` as the steering source of truth.
- Pick one clear throughline.
- Make scene_beats usable by later writing cats.
- Keep every claim anchored to the supplied research.
- Keep all strings short and concrete.
- `evidence_points`, `scene_beats`, and `red_flags` should be brief fragments, not long sentences.
""".strip()

    def _job_packet_has_strong_steering(self, job_packet: dict[str, Any] | None) -> bool:
        if not isinstance(job_packet, dict):
            return False
        strong_keys = {
            "objective",
            "packaging_angle",
            "recommended_angle",
            "script_goal",
            "research_steering",
            "required_evidence",
            "title_formulas",
            "experiment_hypothesis",
        }
        return any(bool(job_packet.get(key)) for key in strong_keys)

    def _load_ledger_context(self) -> dict[str, Any]:
        self.strategy_manager.artifacts_dir = self.workspace_artifacts_dir
        artifact_context = self.strategy_manager.load_global_strategy()
        job_packet = self.strategy_manager.load_job_packet(self.job_id)
        should_use_global_fallback = not self._job_packet_has_strong_steering(job_packet)
        files = list(artifact_context.get("source_files", [])) if should_use_global_fallback else []
        summary = "\n".join((artifact_context.get("evidence_excerpt") or [])[:40])[:5000] if should_use_global_fallback else ""
        global_strategy = artifact_context if should_use_global_fallback else {}
        return {
            "available": bool(job_packet or files or artifact_context),
            "files": files,
            "summary": summary or ("Per-job steering packet is present; global analytics fallback not needed." if job_packet else "No saved Stoic Modernized analytics artifacts were found."),
            "global_strategy": global_strategy,
            "job_packet": job_packet,
        }

    def _build_ledger_prompt(self, research_packet: dict[str, Any], whiskers_brief: dict[str, Any]) -> str:
        ledger_context = self._load_ledger_context()
        return f"""
Research packet:
{json.dumps(research_packet, ensure_ascii=False, indent=2)}

Whiskers brief:
{json.dumps(whiskers_brief, ensure_ascii=False, indent=2)}

Latest channel evidence:
{json.dumps(ledger_context, ensure_ascii=False, indent=2)}

Return JSON only with this exact shape:
{{
  "audience_job": "reach|conversion|balanced",
  "topic_fit": "string",
  "packaging_angle": "string",
  "title_constraints": ["string", "string"],
  "hook_constraints": ["string", "string"],
  "script_constraints": ["string", "string", "string"],
  "distribution_notes": ["string"],
  "experiments": ["string"]
}}

Rules:
- Use `job_packet` / `ledger_packet` as the primary steering source for this specific video.
- Use `global_strategy` only as backup context when the per-job packet is thin.
- Use only the supplied analytics context. If evidence is missing, say so plainly.
- Separate reach vs conversion logic when it matters.
- Keep every list item short, concrete, and operational.
- Recommend constraints that can actually affect title, hook, or narration choices for this video.
""".strip()

    def _build_scratch_prompt(self, research_packet: dict[str, Any], whiskers_brief: dict[str, Any], ledger_strategy: dict[str, Any] | None = None) -> str:
        return f"""
Research packet:
{json.dumps(research_packet, ensure_ascii=False, indent=2)}

Whiskers brief:
{json.dumps(whiskers_brief, ensure_ascii=False, indent=2)}

Ledger strategy:
{json.dumps(ledger_strategy or {}, ensure_ascii=False, indent=2)}

{self._script_json_contract()}

Draft the first full script.
Rules:
{self._script_rules()}
""".strip()

    def _build_tweezers_prompt(self, research_packet: dict[str, Any], draft_script: dict[str, Any], ledger_strategy: dict[str, Any] | None = None) -> str:
        return f"""
Research packet:
{json.dumps(research_packet, ensure_ascii=False, indent=2)}

Scratch draft:
{json.dumps(draft_script, ensure_ascii=False, indent=2)}

Ledger strategy:
{json.dumps(ledger_strategy or {}, ensure_ascii=False, indent=2)}

{self._script_json_contract()}

Revise the script. Improve coherence, specificity, and scene-sized pacing.
Rules:
{self._script_rules()}
- Preserve one coherent thought unit per chapter/scene beat.
- Do not turn this into slogans or generic advice.
""".strip()

    def _build_paw_prompt(self, research_packet: dict[str, Any], script_payload: dict[str, Any], ledger_strategy: dict[str, Any] | None = None) -> str:
        return f"""
Research packet:
{json.dumps(research_packet, ensure_ascii=False, indent=2)}

Script:
{json.dumps(script_payload, ensure_ascii=False, indent=2)}

Ledger strategy:
{json.dumps(ledger_strategy or {}, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "title": "string",
  "hook": "string"
}}

Rules:
- Title must fit Stoic Modernized.
- Hook must be concrete and non-clickbait.
- Match the actual script, not a different angle.
- For shorts, keep the title to 4-9 words.
- For shorts, do not use colons, parentheses, or subtitle-style add-ons.
""".strip()

    def _build_speak_prompt(self, research_packet: dict[str, Any], script_payload: dict[str, Any], paw_hook: dict[str, Any], ledger_strategy: dict[str, Any] | None = None) -> str:
        merged = dict(script_payload)
        merged["title"] = paw_hook.get("title") or merged.get("title")
        merged["hook"] = paw_hook.get("hook") or merged.get("hook")
        return f"""
Research packet:
{json.dumps(research_packet, ensure_ascii=False, indent=2)}

Working script:
{json.dumps(merged, ensure_ascii=False, indent=2)}

Ledger strategy:
{json.dumps(ledger_strategy or {}, ensure_ascii=False, indent=2)}

{self._script_json_contract()}

Rewrite only as needed for spoken delivery.
Rules:
{self._script_rules()}
- Narration must sound natural aloud.
- Preserve coherent scene-sized thought units.
- Keep claims, structure, and meaning intact.
""".strip()

    def _build_mittens_prompt(self, research_packet: dict[str, Any], script_payload: dict[str, Any], ledger_strategy: dict[str, Any] | None = None) -> str:
        return f"""
Research packet:
{json.dumps(research_packet, ensure_ascii=False, indent=2)}

Candidate script:
{json.dumps(script_payload, ensure_ascii=False, indent=2)}

Ledger strategy:
{json.dumps(ledger_strategy or {}, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "approved": true,
  "issues": ["string"],
  "script": {{
    "title": "string",
    "hook": "string",
    "narration": "string",
    "chapters": [{{"title": "string", "timestamp": 0}}],
    "cta": "string"
  }}
}}

Rules:
- If you find fixable issues, fix them in script and approve only if the result is ready.
- Reject if the script is generic, malformed, or not scene-plannable.
- Check title, hook, narration, chapters, and CTA.
- If `retry_feedback` is present in the research packet, treat it as a hard constraint.
- For shorts, reject first-person anecdotes, repeated hook text in later sections, repeated CTA text in the application section, and titles that read like fallback subtitles.
- For shorts, reject preachy, melodramatic, or over-written Stoic language. Prefer plain practical phrasing.
""".strip()

    def _build_mr_jim_prompt(self, research_packet: dict[str, Any], mittens_review: dict[str, Any], ledger_strategy: dict[str, Any] | None = None) -> str:
        return f"""
Research packet:
{json.dumps(research_packet, ensure_ascii=False, indent=2)}

Mittens review:
{json.dumps(mittens_review, ensure_ascii=False, indent=2)}

Ledger strategy:
{json.dumps(ledger_strategy or {}, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "approved": true,
  "issues": ["string"],
  "checks": ["string"],
  "script": {{
    "title": "string",
    "hook": "string",
    "narration": "string",
    "chapters": [{{"title": "string", "timestamp": 0}}],
    "cta": "string"
  }}
}}

Rules:
- This is the operational final check before scene planning.
- Approve only if the script fits Stoic Modernized, the selected video mode, and coherent scene planning.
- The script must be executable by downstream scene generation without reinterpreting its structure.
- If `retry_feedback` is present in the research packet, treat it as a hard constraint.
- For shorts, reject first-person anecdotes, repeated hook text in later sections, repeated CTA text in the application section, titles longer than 9 words, and subtitle-style titles.
- For shorts, reject preachy, melodramatic, or over-written Stoic language. Prefer plain practical phrasing.
""".strip()

    def _build_mr_jim_revision_prompt(
        self,
        research_packet: dict[str, Any],
        mittens_review: dict[str, Any],
        mr_jim_review: dict[str, Any],
        ledger_strategy: dict[str, Any] | None = None,
    ) -> str:
        return f"""
Research packet:
{json.dumps(research_packet, ensure_ascii=False, indent=2)}

Mittens review:
{json.dumps(mittens_review, ensure_ascii=False, indent=2)}

Previous Mr. Jim review:
{json.dumps(mr_jim_review, ensure_ascii=False, indent=2)}

Ledger strategy:
{json.dumps(ledger_strategy or {}, ensure_ascii=False, indent=2)}

Return JSON only:
{{
  "approved": true,
  "issues": ["string"],
  "checks": ["string"],
  "script": {{
    "title": "string",
    "hook": "string",
    "narration": "string",
    "chapters": [{{"title": "string", "timestamp": 0}}],
    "cta": "string"
  }}
}}

Rules:
- Repair the script instead of just critiquing it.
- Resolve every listed issue directly in the returned script.
- Keep the same core topic and Stoic move.
- Return approved=true only if the repaired script is ready for scene planning.
- For shorts: no first-person anecdotes, no repeated hook copied into the Stoic Principle section, no repeated CTA copied into the Workplace Application section.
- For shorts: keep the title to 4-9 words with no colon or parentheses.
- For shorts: keep the narration under about 160 words and paced for ~58 seconds max.
- For shorts: rewrite any preachy, melodramatic, or over-written Stoic language into plain practical language.
""".strip()

    def _script_json_contract(self) -> str:
        if self.video_mode == VideoMode.SHORT:
            chapter_entries = ', '.join([
                '{"title": "Hook", "timestamp": 0}',
                '{"title": "Stoic Principle", "timestamp": 12}',
                '{"title": "Workplace Application", "timestamp": 30}',
                '{"title": "CTA", "timestamp": 50}',
            ])
        else:
            chapter_entries = ", ".join('{"title": "string", "timestamp": number}' for _ in range(5))
        return (
            "Return JSON only with this exact shape:\n"
            "{\n"
            '  "title": "string",\n'
            '  "hook": "string",\n'
            '  "narration": "string",\n'
            f'  "chapters": [{chapter_entries}],\n'
            '  "cta": "string"\n'
            "}"
        )

    def _script_rules(self) -> str:
        if self.video_mode == VideoMode.SHORT:
            return """
- Build ONE coherent throughline, not a list of tips.
- Choose ONE core Stoic move and ONE concrete modern work scenario.
- Write for one person: "you".
- Total narration length: 110-170 words.
- Use complete spoken sentences.
- Do not invent first-person anecdotes, experiments, or personal stories.
- Use plain modern language, not grand speeches.
- Sound calm, practical, and specific.
- No sermon tone. No dramatic metaphors. No lofty lines about the soul, fortress, slavery, sacred boundaries, chaos, machines, or reclaiming your mind.
- Start with a concrete pain point.
- Then name the Stoic principle.
- Then show exactly how to use it at work this week.
- End with a crisp CTA.
- Exactly 4 chapters titled Hook, Stoic Principle, Workplace Application, CTA.
- Use timestamps 0, 12, 30, 50.
- Narration must be formatted as timed blocks like [0:00-0:12] Hook ...
""".strip()
        return """
- Calm, practical, concise tone.
- No academic jargon.
- No unsupported claims.
- Preserve exact qualifiers from research when used.
- Exactly 5 chapters with timestamps 0, 8, 16, 24, 32.
""".strip()

    def _salvage_council_payload(self, content: str) -> dict[str, Any] | None:
        markers = [
            '"title":',
            '"hook":',
            '"narration":',
            '"chapters":',
            '"cta":',
        ]
        if not all(marker in content for marker in markers):
            return None

        def extract_between(start_marker: str, end_marker: str | None) -> str:
            start = content.index(start_marker) + len(start_marker)
            end = len(content) if end_marker is None else content.index(end_marker, start)
            return content[start:end].strip().rstrip(',').strip()

        def clean_string(raw: str) -> str:
            value = raw.strip().rstrip(',').strip()
            if value.startswith('"'):
                value = value[1:]
            if value.endswith('"'):
                value = value[:-1]
            return value.replace('\\n', '\n').replace('\\"', '"').strip()

        try:
            title = clean_string(extract_between('"title":', '"hook":'))
            hook = clean_string(extract_between('"hook":', '"narration":'))
            narration = clean_string(extract_between('"narration":', '"chapters":'))
            chapters_raw = extract_between('"chapters":', '"cta":')
            cta = clean_string(extract_between('"cta":', None))
        except ValueError:
            return None

        chapters: list[dict[str, Any]]
        try:
            chapters = json.loads(chapters_raw.rstrip(','))
        except Exception:
            chapters = [
                {"title": "Hook", "timestamp": 0},
                {"title": "Stoic Principle", "timestamp": 12},
                {"title": "Workplace Application", "timestamp": 30},
                {"title": "CTA", "timestamp": 50},
            ]

        return {
            "title": title,
            "hook": hook,
            "narration": narration,
            "chapters": chapters,
            "cta": cta,
        }

    def _parse_short_timed_sections(self, text: str) -> dict[str, str]:
        pattern = re.compile(
            r"\[(?P<start>\d+:\d{2})-(?P<end>\d+:\d{2})\]\s*(?P<label>[^\n]+)\n(?P<body>.*?)(?=\n\s*\[\d+:\d{2}-\d+:\d{2}\]|\Z)",
            flags=re.DOTALL,
        )
        sections: dict[str, str] = {}
        for match in pattern.finditer(text.strip()):
            label = match.group("label").strip().lower()
            body = " ".join(line.strip() for line in match.group("body").splitlines() if line.strip())
            if "hook" in label:
                sections["hook"] = body
            elif "stoic" in label or "principle" in label:
                sections["principle"] = body
            elif "workplace" in label or "application" in label:
                sections["application"] = body
            elif "cta" in label:
                sections["cta"] = body
        return sections

    def _strip_repeated_edge(self, text: str, repeated: str, *, from_end: bool = False) -> str:
        candidate = " ".join(text.split()).strip()
        repeated_clean = " ".join(repeated.split()).strip()
        if not candidate or not repeated_clean:
            return candidate
        if from_end and candidate.endswith(repeated_clean):
            trimmed = candidate[: -len(repeated_clean)].rstrip(" ,;:-")
            return trimmed.strip()
        if not from_end and candidate.startswith(repeated_clean):
            trimmed = candidate[len(repeated_clean):].lstrip(" ,;:-")
            return trimmed.strip()
        return candidate

    def _strip_visual_directions(self, text: str) -> str:
        cleaned = re.sub(r"\[\s*visual:.*?\]", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\[\s*text overlay:.*?\]", "", cleaned, flags=re.IGNORECASE)
        return " ".join(cleaned.split()).strip()

    def _ensure_cta_handle(self, text: str) -> str:
        candidate = " ".join((text or "").split()).strip()
        if not candidate:
            return "Subscribe to @stoic-modernized for practical Stoic tools you can use at work."
        if "@stoic-modernized" in candidate.lower():
            return candidate
        lowered = candidate.lower().rstrip(".! ")
        if lowered.startswith("subscribe") or lowered.startswith("follow"):
            return "Subscribe to @stoic-modernized for practical Stoic tools you can use at work."
        return f"{candidate.rstrip('.! ')}. Subscribe to @stoic-modernized for practical Stoic tools you can use at work."

    def _normalize_short_narration_blocks(self, hook: str, narration: str, cta: str) -> str:
        text = narration.strip()
        sections = self._parse_short_timed_sections(text)
        if sections:
            hook_text = sections.get("hook") or hook
            principle_text = sections.get("principle") or ""
            application_text = sections.get("application") or ""
            cta_text = sections.get("cta") or cta
        else:
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
            if not paragraphs:
                paragraphs = [text] if text else []

            body = [part for part in paragraphs if part != hook and part != cta]
            if not body and text:
                body = [text]

            hook_text = hook
            principle_text = body[0] if body else ""
            application_text = " ".join(body[1:]).strip() if len(body) > 1 else ""
            cta_text = cta

        hook_text = self._strip_visual_directions(hook_text)
        principle_text = self._strip_visual_directions(principle_text)
        application_text = self._strip_visual_directions(application_text)
        cta_text = self._strip_visual_directions(cta_text)

        principle_text = self._strip_repeated_edge(principle_text, hook_text)
        application_text = self._strip_repeated_edge(application_text, cta_text, from_end=True)

        if principle_text and not application_text:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", principle_text) if s.strip()]
            if len(sentences) >= 3:
                split_at = max(1, len(sentences) // 2)
                principle_text = " ".join(sentences[:split_at]).strip()
                application_text = " ".join(sentences[split_at:]).strip()

        if not hook_text:
            hook_text = principle_text or text
        if not principle_text:
            principle_text = hook_text or text
        if not application_text:
            application_text = text if text not in {hook_text, principle_text} else "Use the Stoic move on the next concrete task in front of you."
        cta_text = self._ensure_cta_handle(cta_text)

        blocks = [
            f"[0:00-0:12] Hook\n{hook_text}".strip(),
            f"[0:12-0:30] Stoic Principle\n{principle_text}".strip(),
            f"[0:30-0:50] Workplace Application\n{application_text}".strip(),
            f"[0:50-0:58] CTA\n{cta_text}".strip(),
        ]
        return "\n\n".join(blocks)

    def _save_council_artifact(self, payload: dict[str, Any]) -> None:
        save_json(payload, self.script_dir / "council_workflow.json")

    def _build_stoic_script_prompt(self, topic: str, research_title: str, key_insights: list, workplace_applications: list, sources: list) -> str:
        """Build prompt for Stoic Modernized script generation."""
        insight_lines = "\n".join(f"- {item}" for item in key_insights[:5]) or "- No insights provided"
        application_lines = "\n".join(f"- {item}" for item in workplace_applications[:5]) or "- No applications provided"
        source_lines = self._format_source_lines(sources[:4])

        if self.video_mode == VideoMode.SHORT:
            prompt = f"""
You are writing a high-retention YouTube Short for Stoic Modernized.

Channel voice: calm, sharp, practical, modern.
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
  "narration": "string",
  "chapters": [
    {{"title": "string", "timestamp": number}},
    {{"title": "string", "timestamp": number}},
    {{"title": "string", "timestamp": number}},
    {{"title": "string", "timestamp": number}}
  ],
  "cta": "string"
}}

SHORT VIDEO RULES:
- Build ONE coherent throughline, not a list of tips.
- Choose ONE core Stoic move and ONE concrete modern work scenario.
- Write for one person: "you". Do not write for "leaders", "organizations", "teams", and "individual contributors" all at once.
- Total narration length: 95-140 words.
- 4 short paragraphs max.
- Use complete sentences, but keep them tight.
- The narration must sound spoken, not like an article summary.
- No generic HR language.
- Avoid phrases like: psychological safety, growth mindset, emotional resets, organizations are updating, individual contributors, economic volatility.
- No listicles. No broad survey of multiple ideas. No abstract corporate sludge.
- No sermon tone. No dramatic metaphors. No grand Stoic cosplay.
- Do not write lines about souls, fortresses, slavery, sacred boundaries, inner citadels, chaos, or destiny.
- Start with a concrete pain point.
- Then name the Stoic principle.
- Then show exactly how to use it at work this week.
- End with a crisp CTA.

TITLE RULES:
- 4-9 words.
- Concrete and sharp.
- No vague self-help phrasing.

HOOK RULES:
- 1-2 sentences.
- Concrete workplace tension.
- No clickbait.

CHAPTER RULES:
- Exactly 4 chapters.
- Timestamps: 0, 5, 10, 15.
- Titles should be short and plain.

CTA RULES:
- One sentence.
- Invite subscription.
- Explicitly mention `@stoic-modernized`.
- Mention practical Stoic tools for work.

No markdown.
Output JSON only.
""".strip()
        else:
            prompt = f"""
You are writing a faceless YouTube script for Stoic Modernized.

Channel voice: Calm, practical, concise. Not preachy. Not academic. Short sentences.
Video mode: {self.video_mode.value}
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
  "title": "string - short, engaging title",
  "hook": "string - 1-2 sentence opening that grabs attention",
  "narration": "string - continuous narration text, broken into natural paragraphs",
  "chapters": [
    {{"title": "string - clear topic heading", "timestamp": number}},
    {{"title": "string - clear topic heading", "timestamp": number}},
    {{"title": "string - clear topic heading", "timestamp": number}},
    {{"title": "string - clear topic heading", "timestamp": number}},
    {{"title": "string - clear topic heading", "timestamp": number}}
  ],
  "cta": "string - call to action inviting subscription"
}}

CRITICAL RULES:
- NEVER repeat words mid-sentence.
- NEVER use double periods or triple periods.
- Write in a calm, practical, concise tone.
- NO academic language or philosophical jargon.
- NO preachy or condescending tone.
- Make points specific to the supplied research.
- Preserve exact numbers, names, and qualifiers from the research when used.
- Do not add unsupported claims.

No markdown.
Output JSON only.
""".strip()

        return prompt

    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM."""
        return """You are an expert scriptwriter for Stoic Modernized, a YouTube channel about practical Stoicism for modern professionals. Write calm, concise, practical scripts that connect ancient wisdom to workplace challenges. Use short sentences. No academic language. No preaching."""

    def _parse_script_response(self, script_data: dict, topic: str) -> Script:
        """Parse LLM response into Script object."""
        script_title = str(script_data.get("title") or f"{topic.title()}: A Stoic Perspective")
        if self.video_mode == VideoMode.SHORT:
            fallback_suffixes = [": A Stoic Perspective", " | Stoic Modernized"]
            for suffix in fallback_suffixes:
                if script_title.endswith(suffix):
                    script_title = script_title[: -len(suffix)].strip()
            if ":" in script_title:
                script_title = script_title.split(":", 1)[0].strip()
            if len(script_title.replace(":", " ").split()) > 9:
                compact_topic = str(topic or "").strip()
                for suffix in fallback_suffixes:
                    if compact_topic.endswith(suffix):
                        compact_topic = compact_topic[: -len(suffix)].strip()
                if ":" in compact_topic:
                    compact_topic = compact_topic.split(":", 1)[0].strip()
                if compact_topic:
                    script_title = compact_topic
        hook = str(script_data.get("hook") or f"What if I told you that 2000 years of wisdom could help you handle {topic} better? Welcome to Stoic Modernized.")
        narration = str(script_data.get("narration") or self._generate_mock_narration(topic))
        cta = self._ensure_cta_handle(str(script_data.get("cta") or "Subscribe to @stoic-modernized for practical Stoic tools you can use at work."))

        if self.video_mode == VideoMode.SHORT and hook:
            sections = self._parse_short_timed_sections(narration)
            hook_already_embedded = False
            if sections:
                embedded_hook = str(sections.get("hook") or "").strip().lower()
                hook_already_embedded = bool(embedded_hook)
            else:
                hook_already_embedded = hook in narration
            if not hook_already_embedded:
                narration = f"{hook}\n\n{narration}".strip()

        # Parse chapters
        chapters = []
        chapter_data = script_data.get("chapters", [])
        chapter_count = 5 if self.video_mode == VideoMode.LONG else 4
        timestamps = [0, 8, 16, 24, 32] if self.video_mode == VideoMode.LONG else [0, 12, 30, 50]
        if isinstance(chapter_data, list):
            for idx, ch in enumerate(chapter_data[:chapter_count]):
                chapter_title = str(ch.get("title") or f"Topic {idx+1}") if isinstance(ch, dict) else f"Topic {idx+1}"
                timestamp = ch.get("timestamp") if isinstance(ch, dict) else timestamps[idx]
                timestamp = timestamps[idx] if timestamp is None else timestamp
                chapters.append(Chapter(title=chapter_title, timestamp=timestamp))

        # If no chapters, generate defaults
        if not chapters:
            for idx in range(chapter_count):
                chapters.append(Chapter(title=f"Topic {idx+1}", timestamp=timestamps[idx]))

        script = Script(
            title=script_title,
            hook=hook,
            narration=narration,
            chapters=chapters,
            cta=cta,
            short_version=narration if self.video_mode == VideoMode.SHORT else self._build_short_version(narration),
            generated_at=datetime.now(UTC),
        )
        self._enforce_generated_script_quality(script)
        self._enforce_script_topic_alignment(script, topic)
        return script

    def _format_source_lines(self, sources: list[str]) -> str:
        """Format research sources into compact lines for the prompt."""
        formatted = []
        for src in sources:
            if isinstance(src, str):
                formatted.append(f"- {src}")
            else:
                formatted.append(f"- {str(src)}")
        return "\n".join(formatted) or "- No sources available"

    def _build_short_version(self, narration: str) -> str:
        """Build a compact short version from narration."""
        sentences = [part.strip() for part in narration.split(".") if part.strip()]
        return ". ".join(sentences[:3]) + ("." if sentences else "")

    def _short_spoken_narration(self, narration: str) -> str:
        sections = self._parse_short_timed_sections(narration or "")
        if sections:
            return " ".join(
                part.strip()
                for part in [
                    sections.get("hook", ""),
                    sections.get("principle", ""),
                    sections.get("application", ""),
                    sections.get("cta", ""),
                ]
                if part and part.strip()
            ).strip()
        cleaned = re.sub(r"\[\d+:\d{2}-\d+:\d{2}\]\s*[^\n]+", "", narration or "")
        return " ".join(cleaned.split()).strip()

    def _word_boundary_contains(self, text: str, term: str) -> bool:
        if not text or not term:
            return False
        return re.search(rf"\b{re.escape(term.lower())}\b", text.lower()) is not None

    def _unexpected_blocked_topic_terms(self, topic: str, script: Script) -> list[str]:
        approved_topic = " ".join((topic or "").split()).lower()
        generated_text = " ".join(
            part.strip()
            for part in [script.title or "", script.hook or "", script.narration or ""]
            if part and part.strip()
        ).lower()
        unexpected: list[str] = []
        for term in sorted(BLOCKED_TOPIC_KEYWORDS):
            if self._word_boundary_contains(generated_text, term) and not self._word_boundary_contains(approved_topic, term):
                unexpected.append(term)
        return unexpected

    def _enforce_generated_script_quality(self, script: Script) -> None:
        """Reject obviously weak generated scripts before they reach later stages."""
        issues = []
        narration = (script.narration or "").strip()
        spoken_narration = self._short_spoken_narration(narration) if self.video_mode == VideoMode.SHORT else narration
        narration_lower = spoken_narration.lower()
        word_count = len(spoken_narration.split())

        if self.video_mode == VideoMode.SHORT:
            if word_count < 60 or word_count > 170:
                issues.append(f"short narration word count out of range: {word_count}")
            if " you " not in f" {narration_lower} ":
                issues.append("short narration does not address the viewer directly")
            title_words = len((script.title or "").replace(":", " ").split())
            if title_words < 4 or title_words > 9:
                issues.append(f"short title word count out of range: {title_words}")
            if ":" in (script.title or ""):
                issues.append("short title looks like a fallback/formal title")
            sections = self._parse_short_timed_sections(narration)
            if sections:
                hook_text = sections.get("hook", "")
                principle_text = sections.get("principle", "")
                application_text = sections.get("application", "")
                cta_text = sections.get("cta", "")
                if hook_text and principle_text.startswith(hook_text):
                    issues.append("stoic-principle section repeats the hook verbatim")
                if cta_text and application_text.endswith(cta_text):
                    issues.append("workplace-application section repeats the CTA verbatim")
            if "[visual:" in narration_lower or "[text overlay:" in narration_lower:
                issues.append("short narration contains visual-direction artifacts")
            if "@stoic-modernized" not in (script.cta or "").lower():
                issues.append("short CTA is missing @stoic-modernized")
            banned_phrases = [
                "psychological safety",
                "growth mindset",
                "individual contributors",
                "organizations are",
                "economic volatility",
                "emotional resets",
                "i once ",
                "i tracked ",
                "i learned ",
                "in my experience",
                "fragmentation of your soul",
                "build a fortress",
                "sacred boundary",
                "slave to the ping",
                "master of your own reaction",
                "chaos of others",
                "failure of will",
                "inner citadel",
                "your only true fortress",
                "surrender your will to the machine",
                "reclaim your mind",
                "silence as a tool",
            ]
            for phrase in banned_phrases:
                if phrase in narration_lower or phrase in (script.title or "").lower():
                    issues.append(f"contains banned generic or fabricated phrase: {phrase.strip()}")
            audience_terms = ["leaders", "organizations", "teams", "employees", "individual contributors"]
            audience_hits = sum(1 for term in audience_terms if term in narration_lower)
            if audience_hits >= 3:
                issues.append("short narration tries to address too many audiences at once")

        if issues:
            raise ScriptGenerationError("Generated script rejected: " + "; ".join(issues))

    def _enforce_script_topic_alignment(self, script: Script, topic: str) -> None:
        unexpected_terms = self._unexpected_blocked_topic_terms(topic, script)
        if unexpected_terms:
            terms = ", ".join(unexpected_terms)
            raise ScriptGenerationError(
                "Generated script rejected: script introduced blocked topic drift "
                f"({terms}) that was not present in the approved research topic '{topic}'."
            )

    def _build_retry_feedback(self, topic: str, error: Exception) -> str:
        message = str(error)
        blocked_terms = re.findall(r"blocked topic drift \((.*?)\)", message)
        if blocked_terms:
            forbidden = blocked_terms[0].strip()
            return (
                f"Previous script drifted away from the approved topic '{topic}' and introduced blocked term(s): {forbidden}. "
                "Generate a new script that stays on the approved topic and does not mention those blocked term(s) in the title, hook, or narration."
            )
        return (
            f"Previous script attempt for approved topic '{topic}' failed validation. "
            "Generate a new script with a materially different title, hook, and narration that stays tightly aligned to the approved topic."
        )

    def _generate_short_narration(self, topic: str) -> str:
        """Generate short narration for short-form video."""
        return f"Stoic wisdom for {topic}. Ancient tools for modern challenges. Practical advice you can use today. Subscribe to @stoic-modernized for more."

    def _generate_mock_narration(self, topic: str) -> str:
        """Generate mock narration for testing."""
        return f"""Welcome to Stoic Modernized. Today we're exploring {topic} through the lens of ancient Stoic wisdom.

The Stoics believed that we cannot control external events, only our response to them. This principle is especially relevant when dealing with {topic} in the workplace.

Consider the words of Marcus Aurelius: "You have power over your mind - not outside events. Realize this, and you will find strength." When facing challenges around {topic}, focus on what you can control: your attitude, your actions, your boundaries.

Practical steps: First, identify what's within your control. Second, accept what isn't. Third, respond with wisdom, not reaction. This approach transforms {topic} from a source of stress into an opportunity for growth.

The key is consistency. Apply these principles daily, and you'll build resilience that serves you in all areas of life."""

    def _short_chapters(self) -> list[Chapter]:
        """Generate chapters for short-form video."""
        return [
            Chapter(title="Hook", timestamp=0.0),
            Chapter(title="Stoic Principle", timestamp=12.0),
            Chapter(title="Workplace Application", timestamp=30.0),
            Chapter(title="CTA", timestamp=50.0),
        ]

    def _long_chapters(self) -> list[Chapter]:
        """Generate chapters for long-form video."""
        return [
            Chapter(title="Introduction", timestamp=0.0),
            Chapter(title="The Stoic Perspective", timestamp=8.0),
            Chapter(title="Modern Workplace Challenge", timestamp=16.0),
            Chapter(title="Practical Solution", timestamp=24.0),
            Chapter(title="Call to Action", timestamp=32.0),
        ]

    def _coerce_string_list(self, value: Any) -> list[str]:
        """Coerce value to list of strings."""
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str):
            return [v.strip() for v in value.split("\n") if v.strip()]
        return []

    def _coerce_sources(self, value: Any) -> list[str]:
        """Coerce research sources into compact prompt-friendly lines."""
        if not isinstance(value, list):
            return self._coerce_string_list(value)
        lines: list[str] = []
        for item in value:
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip()
                note = str(item.get("note") or "").strip()
                if title and note:
                    lines.append(f"{title} — {note}")
                elif title:
                    lines.append(title)
            elif item:
                lines.append(str(item))
        return lines

    def save_script(self, script: Script) -> Path:
        """Save script to file."""
        data = script.model_dump(mode="json")
        data["channel"] = self.channel.value
        data["video_mode"] = self.video_mode.value
        if self.last_steering_chain:
            data["steering_chain"] = self.last_steering_chain
            data["ledger_packet"] = self.last_steering_chain.get("ledger_packet")
            data["whiskers_handoff"] = self.last_steering_chain.get("whiskers_handoff")
            data["whiskers_brief"] = self.last_steering_chain.get("whiskers_brief")
            data["ledger_strategy"] = self.last_steering_chain.get("ledger_strategy")
        return save_json(data, self.script_dir / "script.json")

    def load_script(self) -> Optional[Script]:
        """Load script from file."""
        script_path = self.script_dir / "script.json"
        if not script_path.exists():
            return None

        data = load_json(script_path)
        return Script(**data)
