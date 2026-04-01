"""Scene planning stage module."""

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
        lines = narration.split("\n")
        is_short = len(script_data.get("chapters", [])) <= 4 or len(narration.split()) <= 120

        scenes = []
        scene_num = 1
        current_time = 0.0
        prompts = [
            "vertical composition, minimalist stoic background, ancient roman column silhouette, black marble texture, gold accents, dramatic cinematic lighting, dark philosophical aesthetic, empty center space",
            "vertical composition, ancient roman library, scrolls and columns, warm candlelight, scholarly atmosphere, dark background, gold accents, empty center space",
            "vertical composition, modern office desk with stoic statue, morning light, minimalist, calm atmosphere, dark tones, gold highlights, empty center space",
            "vertical composition, marble bust of stoic philosopher, dramatic side lighting, dark background, philosophical mood, gold accents, empty center space",
            "vertical composition, ancient roman forum ruins, golden hour, contemplative atmosphere, dark tones, subtle gold lighting, empty center space",
        ]

        narration_lines = [line.strip() for line in lines if line.strip() and not line.startswith("[")]
        if is_short and len(narration_lines) > 4:
            narration_lines = [
                narration_lines[0],
                narration_lines[len(narration_lines)//3],
                narration_lines[(2*len(narration_lines))//3],
                narration_lines[-1],
            ]
            lines = narration_lines
        total_words = sum(max(1, len(line.split())) for line in narration_lines) or 1
        target_duration = 54.0 if is_short else None

        for line in lines:
            if line.startswith("[") and "]" in line:
                if not is_short:
                    time_str = line[1:line.index("]")]
                    if "-" in time_str:
                        start_str, _ = time_str.split("-")
                        parts = start_str.split(":")
                        if len(parts) == 2:
                            minutes, seconds = map(float, parts)
                            current_time = minutes * 60 + seconds
                continue

            if line and not line.startswith("[") and line.strip():
                words = max(1, len(line.split()))
                if is_short and target_duration:
                    duration = max(2.0, (target_duration * words / total_words))
                else:
                    duration = len(line.split()) / 2.5
                end_time = current_time + duration

                visual_prompt = prompts[(scene_num - 1) % len(prompts)]
                text_overlay = self._generate_text_overlay(line)

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

        intro_duration = 1.0 if is_short else 3.0
        outro_duration = 1.0 if is_short else 5.0

        intro_scene = Scene(
            scene_number=0,
            start_time=0.0,
            end_time=intro_duration,
            narration_segment="Intro branding",
            visual_prompt="Stoic Modernized channel intro with logo, dark background, gold accents",
            text_overlay="Stoic Modernized",
            animation_style="fade",
        )

        outro_scene = Scene(
            scene_number=len(scenes) + 1,
            start_time=current_time,
            end_time=current_time + outro_duration,
            narration_segment="Outro branding",
            visual_prompt="Stoic Modernized channel outro with subscribe button, dark background, gold accents",
            text_overlay="Subscribe for more",
            animation_style="fade",
        )

        scenes.insert(0, intro_scene)
        scenes.append(outro_scene)

        total_duration = round(current_time + intro_duration + outro_duration, 2)
        if is_short:
            total_duration = min(total_duration, float(settings.short_max_duration_seconds))

        return ScenePlan(
            scenes=scenes,
            intro_duration=intro_duration,
            outro_duration=outro_duration,
            total_duration=total_duration,
        )

    async def _real_scene_plan(self, script_data: dict) -> ScenePlan:
        raise NotImplementedError("Real scene planning requires AI integration")

    def _generate_text_overlay(self, line: str) -> Optional[str]:
        keywords = ["control", "reaction", "strength", "time", "obstacles", "training", "freedom"]
        line_lower = line.lower()

        for keyword in keywords:
            if keyword in line_lower:
                return keyword.title()

        return None

    def save_scene_plan(self, scene_plan: ScenePlan) -> Path:
        data = {
            "job_id": self.job_id,
            "title": settings.channel_name,
            "total_scenes": len(scene_plan.scenes),
            "estimated_duration": scene_plan.total_duration,
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
