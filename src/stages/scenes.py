"""Scene planning stage module."""

import json
import re
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from src.config import Channel, VideoMode, settings
from src.models import Scene, ScenePlan
from src.utils import save_json


class SceneStage:
    """Handles scene planning stage."""

    def __init__(self, job_id: str, mock: bool = False, channel: Channel = settings.default_channel):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.channel = channel
        self.job_dir = settings.jobs_dir / job_id
        self.scenes_dir = self.job_dir / "scenes"
        self.last_steering_context: dict[str, Any] | None = None

    async def run(self, script_data: dict) -> ScenePlan:
        self.scenes_dir.mkdir(parents=True, exist_ok=True)
        self.last_steering_context = self._extract_steering_context(script_data)
        self._initialize_scene_stage_debug_log(script_data)

        if self.mock:
            self._append_scene_stage_debug_log("Scene stage running in mock mode")
            return await self._mock_scene_plan(script_data)
        return await self._real_scene_plan(script_data)

    def _extract_steering_context(self, script_data: dict) -> dict[str, Any]:
        steering_chain = script_data.get("steering_chain") if isinstance(script_data.get("steering_chain"), dict) else {}
        ledger_packet = script_data.get("ledger_packet") if isinstance(script_data.get("ledger_packet"), dict) else steering_chain.get("ledger_packet")
        whiskers_handoff = script_data.get("whiskers_handoff") if isinstance(script_data.get("whiskers_handoff"), dict) else steering_chain.get("whiskers_handoff")
        whiskers_brief = script_data.get("whiskers_brief") if isinstance(script_data.get("whiskers_brief"), dict) else steering_chain.get("whiskers_brief")
        ledger_strategy = script_data.get("ledger_strategy") if isinstance(script_data.get("ledger_strategy"), dict) else steering_chain.get("ledger_strategy")
        return {
            "ledger_packet": ledger_packet or {},
            "whiskers_handoff": whiskers_handoff or {},
            "whiskers_brief": whiskers_brief or {},
            "ledger_strategy": ledger_strategy or {},
        }

    async def _mock_scene_plan(self, script_data: dict) -> ScenePlan:
        narration = script_data.get("narration", "")
        topic = str(script_data.get("title") or script_data.get("topic") or "Stoic modern work").strip()
        explicit_video_mode = str(script_data.get("video_mode") or "").strip().lower()
        is_short = explicit_video_mode == "short" or len(script_data.get("chapters", [])) <= 4 or len(narration.split()) <= 120
        self._append_scene_stage_debug_log(
            f"Baseline input prepared: topic={topic!r}, narration_chars={len(narration)}, narration_words={len(str(narration).split())}, is_short={is_short}"
        )

        scenes = []
        scene_num = 1
        current_time = 0.0
        narration_lines = [line.strip() for line in narration.split("\n") if line.strip() and not line.startswith("[")]
        self._append_scene_stage_debug_log(f"Narration lines extracted: {len(narration_lines)}")
        timed_sections = self._parse_timed_sections(narration)
        self._append_scene_stage_debug_log(f"Timed sections parsed: {len(timed_sections)}")

        if is_short and timed_sections:
            self._append_scene_stage_debug_log("Using timed sections as initial scene specs")
            scene_specs = timed_sections
        else:
            self._append_scene_stage_debug_log("Building scene specs from narration lines")
            scene_specs = self._build_scene_specs_from_lines(narration_lines, is_short=is_short)

        self._append_scene_stage_debug_log(f"Initial scene specs count: {len(scene_specs)}")
        if is_short and scene_specs:
            # Preserve coherent spoken chunks for shorts, aiming for the older 5-6 scene rhythm.
            # Keep one final slot available when the script carries a separate CTA so it is
            # narrated as its own ending instead of becoming a silent visual overlay.
            has_separate_cta = self._should_append_cta_scene(script_data, scene_specs)
            avg_words = sum(max(1, len(str(item.get('text') or '').split())) for item in scene_specs) / max(1, len(scene_specs))
            target_count = min(6, settings.short_target_scene_count)
            expansion_target = max(1, target_count - 1) if has_separate_cta else target_count
            if len(scene_specs) == 1 and avg_words > 45:
                self._append_scene_stage_debug_log(
                    f"Expanding single oversized short scene spec toward target_count={expansion_target}"
                )
                scene_specs = self._expand_short_scene_specs(scene_specs, expansion_target)
                self._append_scene_stage_debug_log(f"Expanded short scene specs count: {len(scene_specs)}")
            elif len(scene_specs) == 2 and avg_words > 18:
                self._append_scene_stage_debug_log("Expanding 2 short scene specs into older 5-6 scene rhythm")
                scene_specs = self._expand_short_scene_specs(scene_specs, expansion_target)
                self._append_scene_stage_debug_log(f"Expanded short scene specs count: {len(scene_specs)}")
            elif len(scene_specs) == 4 and avg_words > 10:
                self._append_scene_stage_debug_log("Expanding 4 timed short sections into ~6 coherent scenes")
                scene_specs = self._expand_short_scene_specs(scene_specs, expansion_target)
                self._append_scene_stage_debug_log(f"Expanded short scene specs count: {len(scene_specs)}")
            else:
                self._append_scene_stage_debug_log("Preserving short scene specs without extra expansion")

        if is_short and self._should_append_cta_scene(script_data, scene_specs):
            cta_text = self._short_cta_text(script_data)
            self._append_scene_stage_debug_log(f"Appending separate narrated CTA scene: {cta_text!r}")
            scene_specs.append({"text": cta_text, "label": "CTA", "scene_type": "cta"})

        total_words = sum(max(1, len(item["text"].split())) for item in scene_specs) or 1
        target_duration = 54.0 if is_short else None

        self._append_scene_stage_debug_log(f"Starting scene object synthesis for {len(scene_specs)} scene specs")
        for spec in scene_specs:
            line = spec["text"]
            scene_type = str(spec.get("scene_type") or "").strip() or None
            title_text = str(spec.get("title_text") or "").strip() or None
            if spec.get("start_time") is not None:
                current_time = float(spec["start_time"])

            if spec.get("end_time") is not None:
                end_time = float(spec["end_time"])
            else:
                words = max(1, len(line.split()))
                if is_short and target_duration:
                    duration = max(2.0, target_duration * words / total_words)
                else:
                    duration = len(line.split()) / 2.5
                end_time = current_time + duration

            visual_seed_text = f"{title_text}. {line}".strip(" .") if scene_type == "story" and title_text else (line or title_text or topic)
            visual_prompt = self._generate_visual_prompt(topic, visual_seed_text, scene_num, is_short, spec.get("label"))
            text_overlay = (
                title_text
                if scene_type in {"title_screen", "story"}
                else self._generate_text_overlay(line, topic, spec.get("label"))
            )

            scenes.append(
                Scene(
                    scene_number=scene_num,
                    start_time=round(current_time, 2),
                    end_time=round(end_time, 2),
                    narration_segment="" if scene_type == "title_screen" else line.strip(),
                    visual_prompt=visual_prompt,
                    text_overlay=text_overlay,
                    animation_style="zoom",
                    scene_type=scene_type,
                    title_text=title_text,
                )
            )

            current_time = end_time
            scene_num += 1

        if is_short and current_time > float(settings.short_max_duration_seconds):
            self._append_scene_stage_debug_log(
                f"Short timing overflow detected ({current_time:.2f}s); compressing to {settings.short_max_duration_seconds}s"
            )
            self._compress_short_scene_timings(scenes, float(settings.short_max_duration_seconds))
            current_time = scenes[-1].end_time if scenes else 0.0

        intro_duration = 0.0 if is_short else 3.0
        outro_duration = 0.0 if is_short else 5.0

        if not is_short:
            intro_visual = f"cinematic intro frame for {topic}, stoic branding, dark background, gold accents"
            intro_text = "Stoic Modernized"
            outro_visual = f"outro frame for {topic}, subscribe moment, elegant stoic composition, dark background, gold accents"
            outro_text = "Subscribe for more"

            intro_scene = Scene(
                scene_number=0,
                start_time=0.0,
                end_time=intro_duration,
                narration_segment="Intro branding",
                visual_prompt=intro_visual,
                text_overlay=intro_text,
                animation_style="fade",
            )

            outro_scene = Scene(
                scene_number=len(scenes) + 1,
                start_time=current_time,
                end_time=current_time + outro_duration,
                narration_segment="Outro branding",
                visual_prompt=outro_visual,
                text_overlay=outro_text,
                animation_style="fade",
            )

            scenes.insert(0, intro_scene)
            scenes.append(outro_scene)

        total_duration = round(current_time + intro_duration + outro_duration, 2)
        if is_short:
            total_duration = min(total_duration, float(settings.short_max_duration_seconds))

        self._append_scene_stage_debug_log(f"Scene object synthesis complete: {len(scenes)} scenes before overlay dedupe")
        self._dedupe_overlays(scenes)
        self._append_scene_stage_debug_log("Overlay dedupe complete; returning baseline scene plan")

        return ScenePlan(
            scenes=scenes,
            intro_duration=intro_duration,
            outro_duration=outro_duration,
            total_duration=total_duration,
            topic=topic,
        )

    async def _real_scene_plan(self, script_data: dict) -> ScenePlan:
        self._append_scene_stage_debug_log("Starting baseline scene plan generation")
        base_plan = await self._mock_scene_plan(script_data)
        self._append_scene_stage_debug_log(f"Baseline scene plan generated with {len(base_plan.scenes)} scenes")
        spoken_scenes = [
            scene
            for scene in base_plan.scenes
            if scene.narration_segment not in {"Intro branding", "Outro branding"}
            and scene.scene_type != "title_screen"
        ]
        if not spoken_scenes:
            self._append_scene_stage_debug_log("No spoken scenes found; returning baseline scene plan")
            return base_plan

        self._append_scene_stage_debug_log(f"Generating local-LLM scene details for {len(spoken_scenes)} spoken scenes")
        planned = await self._generate_scene_details_with_local_llm(script_data, spoken_scenes)
        if not planned:
            self._append_scene_stage_debug_log("Local-LLM scene details unavailable; falling back to baseline scene plan")
            return base_plan

        plan_by_number = {
            int(item["scene_number"]): item
            for item in planned
            if isinstance(item, dict) and isinstance(item.get("scene_number"), int)
        }

        updated_scenes: list[Scene] = []
        for scene in base_plan.scenes:
            replacement = plan_by_number.get(scene.scene_number)
            if replacement:
                updated_scenes.append(
                    Scene(
                        scene_number=scene.scene_number,
                        start_time=scene.start_time,
                        end_time=scene.end_time,
                        narration_segment=scene.narration_segment,
                        visual_prompt=str(replacement.get("visual_prompt") or scene.visual_prompt).strip(),
                        text_overlay=(
                            scene.text_overlay
                            if scene.scene_type in {"title_screen", "story"}
                            else self._normalize_overlay(str(replacement.get("text_overlay") or scene.text_overlay or "")).strip()
                            or scene.text_overlay
                        ),
                        animation_style=str(replacement.get("animation_style") or scene.animation_style or "zoom").strip() or "zoom",
                        scene_type=scene.scene_type,
                        title_text=scene.title_text,
                    )
                )
            else:
                updated_scenes.append(scene)

        self._dedupe_overlays(updated_scenes)
        return ScenePlan(
            scenes=updated_scenes,
            intro_duration=base_plan.intro_duration,
            outro_duration=base_plan.outro_duration,
            total_duration=base_plan.total_duration,
            topic=base_plan.topic,
        )

    async def _generate_scene_details_with_local_llm(
        self, script_data: dict, scenes: list[Scene]
    ) -> list[dict[str, Any]]:
        channel_name = str(script_data.get("channel_name") or script_data.get("channel") or settings.channel_name).strip()
        title = str(script_data.get("title") or script_data.get("topic") or channel_name).strip()
        topic = str(script_data.get("topic") or title).strip()
        is_short = len(scenes) <= settings.short_target_scene_count
        steering_context = self._extract_steering_context(script_data)
        scene_lines = []
        for scene in scenes:
            scene_lines.append(
                {
                    "scene_number": scene.scene_number,
                    "narration_segment": scene.narration_segment,
                    "baseline_visual_prompt": scene.visual_prompt,
                    "baseline_text_overlay": scene.text_overlay,
                    "scene_type": scene.scene_type,
                    "title_text": scene.title_text,
                }
            )

        visual_rule = "prefer modern workplace realism, candid editorial photography, one clear subject, grounded objects"
        prompt = f"""
You are planning scenes for a faceless YouTube video for {channel_name}.

Topic: {topic}
Title: {title}
Mode: {'short vertical video' if is_short else 'long-form video'}
Steering context:
{json.dumps(steering_context, ensure_ascii=False, indent=2)}

Return JSON only in this exact shape:
{{
  "scenes": [
    {{
      "scene_number": 1,
      "visual_prompt": "string",
      "text_overlay": "string",
      "animation_style": "zoom"
    }}
  ]
}}

Rules:
- use `ledger_packet`, `whiskers_handoff`, and `ledger_strategy` as the primary visual steering when present
- return exactly {len(scenes)} scene objects
- keep the same scene_number values provided in the input
- visual_prompt must be concrete and photographable, not abstract
- no references to text, captions, logos, watermarks, titles, or split screens
- {visual_rule}
- text_overlay should be 1-4 words, sharp, natural, and not repetitive
- match the scene visuals to the steering lane and packaging angle when present
- animation_style should usually be "zoom" and occasionally "fade"
- do not change narration text; only plan visuals/overlay
- output JSON only

Input scenes:
{json.dumps(scene_lines, ensure_ascii=False, indent=2)}
""".strip()

        payload = {
            "model": settings.local_scene_model or settings.local_llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You write strict JSON for a video automation pipeline. Respond with JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": settings.local_scene_temperature,
            "max_tokens": settings.local_scene_max_tokens,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        }

        debug_context = self._write_scene_planner_debug_artifacts(payload)

        try:
            async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
                response = await client.post(settings.local_llm_base_url, json=payload)
                self._append_scene_planner_debug_log(
                    debug_context["log_path"],
                    [
                        f"[{datetime.now(UTC).isoformat()}] Response status: {response.status_code}",
                        f"[{datetime.now(UTC).isoformat()}] Response headers: {dict(response.headers)}",
                    ],
                )
                response.raise_for_status()
            data = response.json()
            content = self._extract_message_content(data)
            parsed = json.loads(content)
            self._append_scene_planner_debug_log(
                debug_context["log_path"],
                [
                    f"[{datetime.now(UTC).isoformat()}] Parsed response JSON successfully",
                    f"[{datetime.now(UTC).isoformat()}] Response preview: {self._truncate_debug_value(content)}",
                ],
            )
        except Exception as error:
            self._append_scene_planner_debug_log(
                debug_context["log_path"],
                [
                    f"[{datetime.now(UTC).isoformat()}] Scene planner request failed: {type(error).__name__}: {error}",
                ],
            )
            return []

        raw_scenes = parsed.get("scenes") if isinstance(parsed, dict) else None
        if not isinstance(raw_scenes, list):
            return []

        validated: list[dict[str, Any]] = []
        for item in raw_scenes:
            if not isinstance(item, dict):
                continue
            scene_number = item.get("scene_number")
            if not isinstance(scene_number, int):
                continue
            visual_prompt = str(item.get("visual_prompt") or "").strip()
            text_overlay = self._normalize_overlay(str(item.get("text_overlay") or "").strip())
            animation_style = str(item.get("animation_style") or "zoom").strip() or "zoom"
            if not visual_prompt:
                continue
            validated.append(
                {
                    "scene_number": scene_number,
                    "visual_prompt": visual_prompt,
                    "text_overlay": text_overlay,
                    "animation_style": animation_style,
                }
            )

        if len(validated) != len(scenes):
            return []
        return validated

    def _compress_short_scene_timings(self, scenes: list[Scene], max_duration: float) -> None:
        if not scenes:
            return
        original_total = scenes[-1].end_time
        if original_total <= 0 or original_total <= max_duration:
            return
        scale = max_duration / original_total
        current_start = 0.0
        for index, scene in enumerate(scenes, start=1):
            scaled_duration = max(1.5, (scene.end_time - scene.start_time) * scale)
            if index == len(scenes):
                scene.start_time = round(current_start, 2)
                scene.end_time = round(max_duration, 2)
            else:
                scene.start_time = round(current_start, 2)
                scene.end_time = round(min(max_duration, current_start + scaled_duration), 2)
                if scene.end_time <= scene.start_time:
                    scene.end_time = round(min(max_duration, scene.start_time + 1.5), 2)
            current_start = scene.end_time

    def _initialize_scene_stage_debug_log(self, script_data: dict[str, Any]) -> Path:
        self.scenes_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.scenes_dir / "scene-planner-debug.log"
        title = str(script_data.get("title") or script_data.get("topic") or self.job_id).strip()
        log_lines = [
            f"[{datetime.now(UTC).isoformat()}] Scene stage initialized",
            f"Job ID: {self.job_id}",
            f"Channel: {self.channel.value if isinstance(self.channel, Channel) else self.channel}",
            f"Mock mode: {self.mock}",
            f"Title: {title}",
            "",
        ]
        log_path.write_text("\n".join(log_lines), encoding="utf-8")
        return log_path

    def _append_scene_stage_debug_log(self, message: str) -> None:
        log_path = self.scenes_dir / "scene-planner-debug.log"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{datetime.now(UTC).isoformat()}] {message}\n")

    def _write_scene_planner_debug_artifacts(self, payload: dict[str, Any]) -> dict[str, Path]:
        self.scenes_dir.mkdir(parents=True, exist_ok=True)
        request_path = self.scenes_dir / "scene-planner-request.json"
        log_path = self.scenes_dir / "scene-planner-debug.log"
        request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        curl_command = " ".join(
            [
                "curl",
                "-sS",
                "-X",
                "POST",
                shlex.quote(settings.local_llm_base_url),
                "-H",
                shlex.quote("Content-Type: application/json"),
                "--data-binary",
                shlex.quote(f"@{request_path}"),
            ]
        )

        self._append_scene_stage_debug_log("Preparing local-LLM request payload")
        self._append_scene_planner_debug_log(
            log_path,
            [
                f"[{datetime.now(UTC).isoformat()}] Endpoint: {settings.local_llm_base_url}",
                f"[{datetime.now(UTC).isoformat()}] Timeout seconds: {settings.local_llm_timeout_seconds}",
                f"[{datetime.now(UTC).isoformat()}] Request payload: {request_path}",
                f"[{datetime.now(UTC).isoformat()}] Command:",
                curl_command,
                "",
            ],
        )
        return {"request_path": request_path, "log_path": log_path}

    def _append_scene_planner_debug_log(self, log_path: Path, lines: list[str]) -> None:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    def _truncate_debug_value(self, value: str, limit: int = 400) -> str:
        cleaned = value.strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 3] + "..."

    def _extract_message_content(self, data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text") or ""))
            return "\n".join(part for part in text_parts if part)
        return ""

    def _normalize_overlay(self, overlay: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9' -]+", " ", overlay)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        words = cleaned.split()
        return " ".join(words[:4]).strip()

    def _generate_visual_prompt(
        self, topic: str, line: str, scene_num: int, is_short: bool, label: Optional[str] = None
    ) -> str:
        specific_prompt = self._specific_workplace_visual_prompt(topic, line, scene_num, label)
        if specific_prompt:
            return specific_prompt

        scene_subject = self._scene_subject(line, topic)
        setting = self._scene_setting(line)
        action = self._scene_action(line)
        detail = self._scene_symbol(line)
        if is_short:
            prompt_parts = [
                "vertical 9:16 candid editorial photograph",
                scene_subject,
                setting,
                action,
                detail,
                "one visible workplace moment with concrete props",
                "shallow depth of field, natural office light",
                "no readable text, no logos, no watermark",
            ]
            return ", ".join(part for part in prompt_parts if part)
        return (
            f"cinematic workplace photograph for {topic}, {scene_subject}, {action}, {setting}, {detail}, "
            "specific office props, natural light, no readable text, no logos, no watermark"
        )

    def _specific_workplace_visual_prompt(
        self, topic: str, line: str, scene_num: int, label: Optional[str] = None
    ) -> Optional[str]:
        """Return concrete prompts for recurring workplace-conflict/status beats.

        The generic fallback used to describe a mood ("grounded", "emotionally specific")
        instead of a shootable situation. These templates anchor each beat in a distinct
        photographed moment with roles, props, camera angle, and lighting.
        """
        text = " ".join(part.lower() for part in [topic, line, label or ""] if part)
        if not any(term in text for term in ["status", "validation", "one-up", "ego", "applause", "truth game"]):
            return None

        base_style = "vertical 9:16, candid high-end editorial photograph, shallow depth of field, natural office light, no readable text, no logos, no watermark"

        if any(term in text for term in ["one-up", "meeting", "project", "defend your ego", "heart races"]):
            return (
                "tense glass meeting room immediately after a project debate, one coworker blurred in the background near a blank whiteboard, "
                "seated worker in foreground gripping a pen beside an open notebook and laptop, water glass untouched, chairs slightly askew, "
                f"{base_style}"
            )
        if any(term in text for term in ["opinions", "external", "cannot win", "evolutionary instinct"]):
            return (
                "over-the-shoulder view of a worker pushing a phone with blurred reaction badges away from the keyboard, "
                "open notebook and capped pen kept in the center of the desk, dark monitor glow and city windows behind, "
                f"{base_style}"
            )
        if any(term in text for term in ["validation", "zero-sum", "anxiety", "chasing"]):
            return (
                "lone knowledge worker at the end of a long conference table, smartphone screen turned dark beside a half-open laptop, "
                "one hand resting on a closed notebook instead of reaching for the phone, glass wall reflections and empty chairs behind, "
                f"{base_style}"
            )
        if any(term in text for term in ["challenges", "offering data", "winning the argument", "doing the work"]):
            return (
                "worker sorting anonymous feedback printouts into two neat piles beside a laptop, red pen capped, phone face-down near the edge of the desk, "
                "conference room doorway blurred in the background, posture turned away from the screen, "
                f"{base_style}"
            )
        if any(term in text for term in ["truth game", "integrity", "applause", "urge to react", "craft", "steadiness"]):
            return (
                "close desk-level shot of a worker aligning a single draft page beside a laptop while the phone sits face-down beyond reach, "
                "notification glow blurred on a second monitor, pen placed squarely across the notebook, late-afternoon office light, "
                f"{base_style}"
            )
        if any(term in text for term in ["comments", "subscribe", "let go", "work drama", "today"]):
            return (
                "end-of-day desk scene with closed laptop, access badge turned face-down, dark phone screen, jacket draped over chair, "
                "office windows blue at dusk and hallway lights warming in the background, "
                f"{base_style}"
            )
        return None

    def _generate_text_overlay(self, line: str, topic: str, label: Optional[str] = None) -> Optional[str]:
        line_lower = line.lower()
        if label:
            return label

        phrase_map = [
            ("up to us", "Control Your Part"),
            ("not up to us", "Drop The Rest"),
            ("out of your hands", "Drop The Rest"),
            ("not in your control", "Drop The Rest"),
            ("not yours to command", "Control Your Part"),
            ("preparation and attitude", "Control Your Part"),
            ("best effort", "Best Effort Now"),
            ("stressful email", "Pause The Reply"),
            ("email arrives", "Pause The Reply"),
            ("difficult feedback", "Steady Under Pressure"),
            ("overthinking", "Stop The Spiral"),
            ("replaying", "Replay Loop"),
            ("meeting", "After The Meeting"),
            ("presentation", "Steady Delivery"),
            ("control", "What You Control"),
            ("reaction", "Own Your Response"),
            ("response", "Own Your Response"),
            ("anxiety", "Pause First"),
            ("clarity", "Clear Next Step"),
            ("subscribe", "Use This Today"),
            ("follow", "Use This Today"),
            ("training", "Train Composure"),
            ("focus", "Protect Focus"),
        ]

        for keyword, overlay in phrase_map:
            if keyword in line_lower:
                return overlay

        fallback_words = [
            word.title()
            for word in re.findall(r"[A-Za-z]+", line)
            if len(word) > 3 and word.lower() not in self._overlay_stopwords()
        ]
        if fallback_words:
            return " ".join(fallback_words[:2])

        topic_words = [word for word in topic.replace(":", " ").split() if len(word) > 4]
        if topic_words:
            return topic_words[0].title()
        return None

    def _parse_timed_sections(self, narration: str) -> list[dict[str, object]]:
        pattern = re.compile(
            r"^\[(?P<start>\d+:\d{2})-(?P<end>\d+:\d{2})\]\s*(?P<label>.+?)\n(?P<body>.*?)(?=\n\[\d+:\d{2}-\d+:\d{2}\]|\Z)",
            flags=re.DOTALL | re.MULTILINE,
        )
        sections: list[dict[str, object]] = []
        for match in pattern.finditer(narration.strip()):
            body = " ".join(line.strip() for line in match.group("body").splitlines() if line.strip())
            raw_label = match.group("label").strip()
            section_type = self._section_type(raw_label)
            title_text = self._section_title_text(raw_label, body, section_type)
            if not body and section_type != "title_screen":
                continue
            normalized_label = self._normalize_section_label(raw_label, body)
            sections.append(
                {
                    "start_time": self._parse_mmss(match.group("start")),
                    "end_time": self._parse_mmss(match.group("end")),
                    "label": title_text or normalized_label,
                    "text": "" if section_type == "title_screen" else body,
                    "scene_type": section_type,
                    "title_text": body if section_type == "title_screen" else title_text,
                }
            )
        return sections

    def _short_cta_text(self, script_data: dict) -> str:
        """Return the established Stoic Modernized short CTA text.

        Short renders already have a branded subscribe end card. Keep the spoken CTA
        aligned with the channel default instead of allowing per-script micro-CTAs to
        invent a different ending style.
        """
        return settings.get_channel_cta(self.channel).strip() or str(script_data.get("cta") or "").strip()

    def _should_append_cta_scene(self, script_data: dict, scene_specs: list[dict[str, object]]) -> bool:
        cta_text = self._short_cta_text(script_data)
        if not cta_text:
            return False
        normalized_cta = self._normalize_spoken_text(cta_text)
        if not normalized_cta:
            return False
        existing = self._normalize_spoken_text(
            " ".join(str(spec.get("text") or "") for spec in scene_specs)
        )
        return normalized_cta not in existing

    def _normalize_spoken_text(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    def _build_scene_specs_from_lines(self, lines: list[str], *, is_short: bool) -> list[dict[str, object]]:
        if not lines:
            return []
        if not is_short:
            return [{"text": line} for line in lines]

        count = min(settings.short_target_scene_count, len(lines))
        if count == len(lines):
            return [{"text": line} for line in lines]

        indexes = sorted({round(i * (len(lines) - 1) / max(1, count - 1)) for i in range(count)})
        return [{"text": lines[index]} for index in indexes]

    def _expand_short_scene_specs(self, scene_specs: list[dict[str, object]], target_count: int) -> list[dict[str, object]]:
        if not scene_specs:
            return []
        if len(scene_specs) >= target_count:
            return scene_specs[:target_count]

        allocations = self._allocate_short_scene_counts(scene_specs, target_count)
        expanded: list[dict[str, object]] = []

        for spec, pieces in zip(scene_specs, allocations, strict=False):
            text = str(spec.get("text") or "").strip()
            if not text:
                continue

            beats = self._split_text_into_visual_beats(text, pieces)
            start_time = spec.get("start_time")
            end_time = spec.get("end_time")
            label = spec.get("label")

            if (
                isinstance(start_time, (int, float))
                and isinstance(end_time, (int, float))
                and end_time > start_time
                and beats
            ):
                beat_word_counts = [max(1, len(beat.split())) for beat in beats]
                total_words = sum(beat_word_counts) or 1
                cursor = float(start_time)
                for index, beat in enumerate(beats):
                    duration = (float(end_time) - float(start_time)) * (beat_word_counts[index] / total_words)
                    beat_end = float(end_time) if index == len(beats) - 1 else cursor + duration
                    expanded.append(
                        {
                            "text": beat,
                            "start_time": round(cursor, 3),
                            "end_time": round(beat_end, 3),
                            "label": label if pieces == 1 else None,
                        }
                    )
                    cursor = beat_end
            else:
                expanded.extend({"text": beat, "label": label if pieces == 1 else None} for beat in beats)

        return expanded[:target_count]

    def _allocate_short_scene_counts(self, scene_specs: list[dict[str, object]], target_count: int) -> list[int]:
        allocations = [1 for _ in scene_specs]
        extra = max(0, target_count - len(scene_specs))
        word_counts = [max(1, len(str(spec.get("text") or "").split())) for spec in scene_specs]

        for _ in range(extra):
            best_index = max(
                range(len(scene_specs)),
                key=lambda i: word_counts[i] / allocations[i],
            )
            allocations[best_index] += 1

        return allocations

    def _split_text_into_visual_beats(self, text: str, pieces: int) -> list[str]:
        cleaned = " ".join(text.split())
        if pieces <= 1 or not cleaned:
            return [cleaned]

        units = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", cleaned) if segment.strip()]
        if not units:
            units = [cleaned]

        while len(units) < pieces:
            split_index = max(range(len(units)), key=lambda i: len(units[i].split()))
            candidate = units[split_index]
            parts = self._split_long_unit(candidate)
            if len(parts) < 2:
                break
            units = units[:split_index] + parts + units[split_index + 1 :]

        if len(units) <= pieces:
            return units[:pieces]

        total_words = sum(max(1, len(unit.split())) for unit in units)
        target_words = max(1, total_words / pieces)
        grouped: list[str] = []
        current: list[str] = []
        current_words = 0
        remaining_units = len(units)

        for unit in units:
            unit_words = max(1, len(unit.split()))
            remaining_units -= 1
            remaining_slots = pieces - len(grouped)
            should_flush = (
                current
                and current_words + unit_words > target_words
                and remaining_units >= max(0, remaining_slots - 1)
            )
            if should_flush:
                grouped.append(" ".join(current).strip())
                current = [unit]
                current_words = unit_words
            else:
                current.append(unit)
                current_words += unit_words

        if current:
            grouped.append(" ".join(current).strip())

        if len(grouped) > pieces:
            tail = " ".join(grouped[pieces - 1 :]).strip()
            grouped = grouped[: pieces - 1] + [tail]

        return grouped

    def _split_long_unit(self, text: str) -> list[str]:
        """Split a long narration unit into two coherent spoken chunks."""
        candidate = text.strip()
        if not candidate:
            return [candidate]

        split_patterns = [
            r"\s+(?:Instead,|Then,|So,|That way,|This shift|This move|Try this|When )",
            r"(?<=[,;:])\s+(?=(?:instead|then|so|when|write|visualize|stop|focus)\b)",
        ]
        for pattern in split_patterns:
            parts = [part.strip() for part in re.split(pattern, candidate, maxsplit=1) if part.strip()]
            if len(parts) == 2 and all(len(part.split()) >= 6 for part in parts):
                return parts

        words = candidate.split()
        if len(words) < 14:
            return [candidate]

        midpoint = len(words) // 2
        for offset in range(0, min(6, len(words) // 3 + 1)):
            for pivot in (midpoint - offset, midpoint + offset):
                if 6 <= pivot <= len(words) - 6:
                    return [" ".join(words[:pivot]), " ".join(words[pivot:])]
        return [candidate]

    def _parse_mmss(self, value: str) -> float:
        minutes, seconds = value.split(":", 1)
        return int(minutes) * 60 + int(seconds)

    def _normalize_section_label(self, label: str, line: str) -> str:
        normalized = self._generate_text_overlay(line, "", label=None)
        if normalized:
            return normalized
        return self._clean_label(label)

    def _section_type(self, label: str) -> Optional[str]:
        lowered = str(label).strip().lower()
        if "title screen" in lowered:
            return "title_screen"
        if "title announcement" in lowered:
            return "title_announcement"
        if re.match(r"section\s+[2-6]:", lowered):
            return "story"
        if re.match(r"section\s+7:\s*cta", lowered):
            return "cta"
        return None

    def _section_title_text(self, label: str, body: str, section_type: Optional[str]) -> Optional[str]:
        if section_type == "title_screen":
            return body or None
        if section_type == "story":
            match = re.match(r"Section\s+[2-6]:\s*(.+)$", str(label).strip(), flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _clean_label(self, value: str) -> str:
        words = [word for word in re.findall(r"[A-Za-z]+", value) if word.lower() not in self._overlay_stopwords()]
        return " ".join(word.title() for word in words[:3]) or "Stoic Shift"

    def _overlay_stopwords(self) -> set[str]:
        return {
            "about",
            "after",
            "before",
            "from",
            "have",
            "into",
            "just",
            "more",
            "over",
            "that",
            "this",
            "your",
            "with",
            "they",
            "them",
            "what",
            "when",
            "where",
            "will",
            "would",
            "should",
            "could",
            "stoic",
            "modernized",
            "marcus",
            "aurelius",
            "seneca",
            "epictetus",
            "reminded",
            "office",
            "workplace",
            "signal",
            "news",
            "video",
            "today",
        }

    def _scene_subject(self, line: str, topic: str) -> str:
        line_lower = line.lower()
        if self._line_has_control_split(line_lower):
            return "professional at desk weighing a checklist against incoming feedback"
        if "presentation" in line_lower:
            return "professional standing with presentation remote and note card"
        if "meeting" in line_lower:
            return "office worker alone at desk after a tense meeting"
        if "boss" in line_lower or "manager" in line_lower or "client" in line_lower:
            return "professional facing difficult feedback on a laptop screen"
        if "task" in line_lower or "focus" in line_lower:
            return "worker returning to a single task on a clean desk"
        if "anxiety" in line_lower or "pause" in line_lower:
            return "professional taking one steady breath before responding"
        return "worker in a photographed workplace moment tied to the concrete scene"

    def _scene_setting(self, line: str) -> str:
        line_lower = line.lower()
        if self._line_has_control_split(line_lower):
            return "desk with laptop feedback open beside a handwritten to-do list"
        if "presentation" in line_lower:
            return "conference room moments before speaking"
        if "meeting" in line_lower:
            return "desk lit by laptop glow after coworkers leave"
        if "boss" in line_lower or "manager" in line_lower:
            return "open-plan office with message notifications nearby"
        if "deadline" in line_lower or "task" in line_lower:
            return "focused workstation with notebook and calendar"
        return "specific desk, meeting room, or commute location implied by the narration"

    def _scene_action(self, line: str) -> str:
        line_lower = line.lower()
        if "replay" in line_lower or "overthinking" in line_lower:
            return "visual tension showing repeated thoughts circling the subject"
        if self._line_has_control_split(line_lower):
            return "clear contrast between what can be acted on and what must be released"
        if "pause" in line_lower or "breath" in line_lower:
            return "subtle pause before action"
        if "control" in line_lower or "in my hands" in line_lower:
            return "clear contrast between prepared actions and blurred external noise"
        if "presentation" in line_lower:
            return "calm posture before delivering the message"
        if "release" in line_lower or "clarity" in line_lower:
            return "notebook centered while phone and laptop noise sit out of reach"
        return "one visible choice in progress: phone pushed away, pen gripped, laptop closed, or notes sorted"

    def _scene_symbol(self, line: str) -> str:
        line_lower = line.lower()
        if "overthinking" in line_lower or "loop" in line_lower:
            return "subtle looping reflections in glass or screen"
        if self._line_has_control_split(line_lower):
            return "simple checklist in sharp focus while notifications blur into the background"
        if "control" in line_lower:
            return "simple checklist and neatly arranged notes"
        if "presentation" in line_lower:
            return "single spotlight and tidy slide clicker"
        if "clarity" in line_lower:
            return "calm desk surface with one open notebook"
        if "subscribe" in line_lower or "daily" in line_lower:
            return "closed laptop, access badge, and bag gathered at the desk edge"
        return "specific props in frame: face-down phone, capped pen, notebook, water glass, or feedback pages"

    def _dedupe_overlays(self, scenes: list[Scene]) -> None:
        seen: set[str] = set()
        for scene in scenes:
            if not scene.text_overlay:
                continue
            original = scene.text_overlay.strip()
            candidate = original
            suffix = 2
            while candidate.lower() in seen:
                candidate = self._variant_overlay(original, scene.narration_segment, suffix)
                suffix += 1
            scene.text_overlay = candidate
            seen.add(candidate.lower())

    def _variant_overlay(self, overlay: str, narration_segment: str, suffix: int) -> str:
        narration = narration_segment.lower()
        variants = {
            "what you control": ["Control Your Part", "Act On Your Part", "Control The Next Step"],
            "own your response": ["Choose Your Response", "Hold Your Composure", "Respond With Clarity"],
            "use this today": ["Try This Today", "Practice This Today", "Use It Today"],
            "pause first": ["Take The Beat", "Breathe Before Reply", "Pause The Spiral"],
        }
        choices = variants.get(overlay.lower(), [])
        if choices:
            index = min(suffix - 2, len(choices) - 1)
            choice = choices[index]
            if choice.lower() != overlay.lower() or len(choices) > 1:
                return choice
        if "control" in narration:
            return "Control The Next Step"
        if "response" in narration or "react" in narration:
            return "Choose Your Response"
        if "follow" in narration or "subscribe" in narration:
            return "Try This Today"

        words = [word for word in overlay.split() if word]
        if len(words) >= 2:
            return " ".join(words[:3] + [str(suffix)])
        if overlay.strip():
            return f"{overlay.strip()} {suffix}"
        return f"Scene {suffix}"

    def _line_has_control_split(self, line_lower: str) -> bool:
        control_markers = [
            "up to us",
            "not up to us",
            "out of your hands",
            "not yours to command",
            "preparation and attitude",
            "best effort",
            "what is in my control",
            "what is actually under your control",
        ]
        return any(marker in line_lower for marker in control_markers)

    def save_scene_plan(self, scene_plan: ScenePlan) -> Path:
        data = {
            "job_id": self.job_id,
            "title": settings.get_channel_name(self.channel),
            "topic": getattr(scene_plan, "topic", settings.channel_name),
            "total_scenes": len(scene_plan.scenes),
            "estimated_duration": scene_plan.total_duration,
            "intro_duration": scene_plan.intro_duration,
            "outro_duration": scene_plan.outro_duration,
            "total_duration": scene_plan.total_duration,
            "steering_context": self.last_steering_context,
            "scenes": [s.model_dump() for s in scene_plan.scenes],
            "generated_at": datetime.now(UTC).isoformat(),
        }
        return save_json(data, self.scenes_dir / "scenes.json")

    def load_scene_plan(self) -> Optional[ScenePlan]:
        scenes_path = self.scenes_dir / "scenes.json"
        if not scenes_path.exists():
            return None

        from src.utils import load_json

        data = load_json(scenes_path)
        scenes = [Scene(**s) for s in data.get("scenes", [])]
        return ScenePlan(
            scenes=scenes,
            intro_duration=data.get("intro_duration", 3.0),
            outro_duration=data.get("outro_duration", 5.0),
            total_duration=data.get("total_duration", 0.0),
        )
