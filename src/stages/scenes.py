"""Scene planning stage module."""

import re
from pathlib import Path
from typing import Optional

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
            scene_specs = scene_specs[:4]

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
        raise NotImplementedError("Real scene planning requires AI integration")

    def _generate_visual_prompt(
        self, topic: str, line: str, scene_num: int, is_short: bool, label: Optional[str] = None
    ) -> str:
        scene_subject = self._scene_subject(line, topic)
        setting = self._scene_setting(line)
        action = self._scene_action(line)
        detail = self._scene_symbol(line)
        if is_short:
            return (
                f"vertical 9:16 frame, {scene_subject}, {action}, {setting}, {detail}, "
                f"topic context {topic}, one clear focal subject, concrete workplace storytelling, no text, no logo"
            )
        return (
            f"cinematic workplace scene for {topic}, {scene_subject}, {action}, {setting}, {detail}, "
            "grounded modern environment, no text, no logo"
        )

    def _generate_text_overlay(self, line: str, topic: str, label: Optional[str] = None) -> Optional[str]:
        line_lower = line.lower()
        if label:
            return label

        phrase_map = [
            ("overthinking", "Stop The Spiral"),
            ("replaying", "Replay Loop"),
            ("meeting", "After The Meeting"),
            ("presentation", "Steady Delivery"),
            ("control", "What You Control"),
            ("reaction", "Own Your Response"),
            ("response", "Own Your Response"),
            ("anxiety", "Pause First"),
            ("clarity", "Clear Next Step"),
            ("subscribe", "Practice Daily"),
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

        count = min(4, len(lines))
        if count == len(lines):
            return [{"text": line} for line in lines]

        indexes = sorted({round(i * (len(lines) - 1) / max(1, count - 1)) for i in range(count)})
        return [{"text": lines[index]} for index in indexes]

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
        }

    def _scene_subject(self, line: str, topic: str) -> str:
        line_lower = line.lower()
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
        seen: dict[str, int] = {}
        for scene in scenes:
            if not scene.text_overlay:
                continue
            key = scene.text_overlay.lower()
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                scene.text_overlay = f"{scene.text_overlay} {seen[key]}"

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
            "generated_at": "TODO: Add timestamp",
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
