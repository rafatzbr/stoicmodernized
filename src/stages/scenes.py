"""Scene planning stage module."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from src.config import VideoMode, settings
from src.models import Scene, ScenePlan
from src.utils import save_json


class SceneStage:
    """Handles scene planning stage."""

    def __init__(self, job_id: str, mock: bool = False):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.job_dir = settings.jobs_dir / job_id
        self.scenes_dir = self.job_dir / "scenes"

    async def run(self, script_data: dict) -> ScenePlan:
        self.scenes_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._mock_scene_plan(script_data)
        return await self._real_scene_plan(script_data)

    async def _mock_scene_plan(self, script_data: dict) -> ScenePlan:
        narration = script_data.get("narration", "")
        topic = str(script_data.get("title") or script_data.get("topic") or "Stoic modern work").strip()
        is_short = len(script_data.get("chapters", [])) <= 4 or len(narration.split()) <= 120

        scenes = []
        scene_num = 1
        current_time = 0.0
        narration_lines = [line.strip() for line in narration.split("\n") if line.strip() and not line.startswith("[")]
        timed_sections = self._parse_timed_sections(narration)

        if is_short and timed_sections:
            scene_specs = timed_sections
        else:
            scene_specs = self._build_scene_specs_from_lines(narration_lines, is_short=is_short)

        if is_short and scene_specs:
            scene_specs = self._expand_short_scene_specs(scene_specs, settings.short_target_scene_count)

        total_words = sum(max(1, len(item["text"].split())) for item in scene_specs) or 1
        target_duration = 54.0 if is_short else None

        for spec in scene_specs:
            line = spec["text"]
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

            visual_prompt = self._generate_visual_prompt(topic, line, scene_num, is_short, spec.get("label"))
            text_overlay = self._generate_text_overlay(line, topic, spec.get("label"))

            scenes.append(
                Scene(
                    scene_number=scene_num,
                    start_time=round(current_time, 2),
                    end_time=round(end_time, 2),
                    narration_segment=line.strip(),
                    visual_prompt=visual_prompt,
                    text_overlay=text_overlay,
                    animation_style="zoom",
                )
            )

            current_time = end_time
            scene_num += 1

        intro_duration = 0.0 if is_short else 3.0
        outro_duration = 0.0 if is_short else 5.0

        if not is_short:
            intro_scene = Scene(
                scene_number=0,
                start_time=0.0,
                end_time=intro_duration,
                narration_segment="Intro branding",
                visual_prompt=f"cinematic intro frame for {topic}, stoic branding, dark background, gold accents",
                text_overlay="Stoic Modernized",
                animation_style="fade",
            )

            outro_scene = Scene(
                scene_number=len(scenes) + 1,
                start_time=current_time,
                end_time=current_time + outro_duration,
                narration_segment="Outro branding",
                visual_prompt=f"outro frame for {topic}, subscribe moment, elegant stoic composition, dark background, gold accents",
                text_overlay="Subscribe for more",
                animation_style="fade",
            )

            scenes.insert(0, intro_scene)
            scenes.append(outro_scene)

        total_duration = round(current_time + intro_duration + outro_duration, 2)
        if is_short:
            total_duration = min(total_duration, float(settings.short_max_duration_seconds))

        self._dedupe_overlays(scenes)

        return ScenePlan(
            scenes=scenes,
            intro_duration=intro_duration,
            outro_duration=outro_duration,
            total_duration=total_duration,
            topic=topic,
        )

    async def _real_scene_plan(self, script_data: dict) -> ScenePlan:
        base_plan = await self._mock_scene_plan(script_data)
        spoken_scenes = [
            scene for scene in base_plan.scenes if scene.narration_segment not in {"Intro branding", "Outro branding"}
        ]
        if not spoken_scenes:
            return base_plan

        planned = await self._generate_scene_details_with_local_llm(script_data, spoken_scenes)
        if not planned:
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
                        text_overlay=self._normalize_overlay(str(replacement.get("text_overlay") or scene.text_overlay or "")).strip()
                        or scene.text_overlay,
                        animation_style=str(replacement.get("animation_style") or scene.animation_style or "zoom").strip() or "zoom",
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
        title = str(script_data.get("title") or script_data.get("topic") or settings.channel_name).strip()
        topic = str(script_data.get("topic") or title).strip()
        is_short = len(scenes) <= settings.short_target_scene_count
        scene_lines = []
        for scene in scenes:
            scene_lines.append(
                {
                    "scene_number": scene.scene_number,
                    "narration_segment": scene.narration_segment,
                    "baseline_visual_prompt": scene.visual_prompt,
                    "baseline_text_overlay": scene.text_overlay,
                }
            )

        prompt = f"""
You are planning scenes for a faceless YouTube video for {settings.channel_name}.

Topic: {topic}
Title: {title}
Mode: {'short vertical video' if is_short else 'long-form video'}

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
- return exactly {len(scenes)} scene objects
- keep the same scene_number values provided in the input
- visual_prompt must be concrete and photographable, not abstract
- no references to text, captions, logos, watermarks, titles, or split screens
- prefer modern workplace realism, candid editorial photography, one clear subject, grounded objects
- text_overlay should be 1-4 words, sharp, natural, and not repetitive
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

        try:
            async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
                response = await client.post(settings.local_llm_base_url, json=payload)
                response.raise_for_status()
            data = response.json()
            content = self._extract_message_content(data)
            parsed = json.loads(content)
        except Exception:
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
        scene_subject = self._scene_subject(line, topic)
        setting = self._scene_setting(line)
        action = self._scene_action(line)
        detail = self._scene_symbol(line)
        if is_short:
            prompt_parts = [
                "vertical 9:16 frame",
                scene_subject,
                setting,
                action,
                detail,
                f"workplace context: {topic}",
                "single focal subject",
                "modern editorial photo",
                "no text",
                "no logo",
            ]
            return ", ".join(part for part in prompt_parts if part)
        return (
            f"cinematic workplace scene for {topic}, {scene_subject}, {action}, {setting}, {detail}, "
            "grounded modern environment, no text, no logo"
        )

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
            if not body:
                continue
            sections.append(
                {
                    "start_time": self._parse_mmss(match.group("start")),
                    "end_time": self._parse_mmss(match.group("end")),
                    "label": self._normalize_section_label(match.group("label"), body),
                    "text": body,
                }
            )
        return sections

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
            parts = [part.strip() for part in re.split(r"(?<=[,;:])\s+|\s+(?:but|and|while|yet|instead|because)\s+", candidate, maxsplit=1) if part.strip()]
            if len(parts) < 2:
                words = candidate.split()
                if len(words) < 8:
                    break
                midpoint = len(words) // 2
                parts = [" ".join(words[:midpoint]), " ".join(words[midpoint:])]
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

    def _parse_mmss(self, value: str) -> float:
        minutes, seconds = value.split(":", 1)
        return int(minutes) * 60 + int(seconds)

    def _normalize_section_label(self, label: str, line: str) -> str:
        normalized = self._generate_text_overlay(line, "", label=None)
        if normalized:
            return normalized
        return self._clean_label(label)

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
        return f"modern office professional dealing with {topic.lower()}"

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
        return "grounded contemporary office environment"

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
            return "sense of mental release and sharper focus"
        return "emotionally specific action tied to the narrated moment"

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
            return "confident upward motion and renewed momentum"
        return "small symbolic props that support the idea without text"

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
            return choices[index]
        if "control" in narration:
            return "Control The Next Step"
        if "response" in narration or "react" in narration:
            return "Choose Your Response"
        if "follow" in narration or "subscribe" in narration:
            return "Try This Today"
        return overlay

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
            "title": settings.channel_name,
            "topic": getattr(scene_plan, "topic", settings.channel_name),
            "total_scenes": len(scene_plan.scenes),
            "estimated_duration": scene_plan.total_duration,
            "intro_duration": scene_plan.intro_duration,
            "outro_duration": scene_plan.outro_duration,
            "total_duration": scene_plan.total_duration,
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
