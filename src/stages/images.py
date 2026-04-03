"""Image generation stage module using stable diffusion CLI or local fallbacks."""

import subprocess
from pathlib import Path
from typing import Optional

from src.config import settings
from src.models import ImageAsset


class ImageGenerationError(RuntimeError):
    """Raised when real image generation fails."""


class ImageGenerationStage:
    """Handles image generation for scenes."""

    def __init__(self, job_id: str, mock: bool = False, placeholder_only: bool = False):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.placeholder_only = placeholder_only or settings.force_placeholder_images
        self.job_dir = settings.jobs_dir / job_id
        self.images_dir = self.job_dir / "images"

        self.sd_cli_path = settings.sd_cli_path
        self.sd_model_path = settings.sd_model_path
        self.sd_clip_l_path = settings.sd_clip_l_path
        self.sd_clip_g_path = settings.sd_clip_g_path
        self.sd_t5xxl_path = settings.sd_t5xxl_path
        self.sd_width = settings.sd_image_width
        self.sd_height = settings.sd_image_height
        self.sd_cfg_scale = settings.sd_cfg_scale
        self.sd_sampling_method = settings.sd_sampling_method

    async def run(self, scene_plan: dict) -> list[ImageAsset]:
        self.images_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._generate_placeholder_images(scene_plan, style="mock")

        if self.placeholder_only:
            return await self._generate_placeholder_images(scene_plan, style="local")

        if self._sd_cli_available():
            return await self._real_generate(scene_plan)

        raise ImageGenerationError(
            "sd_cli_unavailable: stable diffusion CLI or model files are missing; use --placeholder-images if you want local placeholder cards"
        )

    def _sd_cli_available(self) -> bool:
        return Path(self.sd_cli_path).exists() and Path(self.sd_model_path).exists()

    def _extract_subject(self, scene_plan: dict) -> str:
        topic = scene_plan.get("topic") if isinstance(scene_plan, dict) else None
        if isinstance(topic, str) and topic.strip():
            return topic.strip()

        scenes = scene_plan.get("scenes", []) if isinstance(scene_plan, dict) else []
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            for key in ("text_overlay", "narration_segment", "visual_prompt"):
                value = scene.get(key)
                if isinstance(value, str) and value.strip() and value.strip().lower() not in {"intro branding", "outro branding"}:
                    return value.strip()[:120]
        return "stoic modern work"

    async def _generate_placeholder_images(
        self, scene_plan: dict, style: str = "local"
    ) -> list[ImageAsset]:
        assets = []
        subject = self._extract_subject(scene_plan)
        for scene in scene_plan.get("scenes", []):
            image_path = self.images_dir / f"scene_{scene['scene_number']:03d}.jpg"
            scene_prompt = scene.get("visual_prompt", "Stoic visual")
            focused_prompt = f"subject: {subject} | scene: {scene_prompt}"
            self._create_scene_card(
                image_path=image_path,
                title=f"Scene {scene['scene_number']:03d}",
                prompt=focused_prompt,
                overlay=scene.get("text_overlay") or subject,
                style=style,
            )
            assets.append(
                ImageAsset(
                    scene_number=scene["scene_number"],
                    image_path=str(image_path),
                    prompt=focused_prompt,
                    seed=-1,
                )
            )

        return assets

    async def _real_generate(self, scene_plan: dict) -> list[ImageAsset]:
        assets = []
        subject = self._extract_subject(scene_plan)
        negative_prompt = "people, face, crowd, beach, ocean, water, snow, text, logo, border, frame, margin, white border, blank edge, poster, flyer"

        for scene in scene_plan.get("scenes", []):
            scene_num = scene["scene_number"]
            image_path = self.images_dir / f"scene_{scene_num:03d}.jpg"
            scene_prompt = scene.get("visual_prompt", "")
            full_prompt = self._compose_image_prompt(
                subject=subject,
                scene_prompt=scene_prompt,
                overlay=scene.get("text_overlay"),
            )

            try:
                await self._generate_single_image(
                    prompt=full_prompt,
                    output_path=image_path,
                    negative_prompt=negative_prompt,
                )
                self._postprocess_generated_image(image_path)
            except Exception as exc:
                raise ImageGenerationError(
                    f"image_generation_failed_for_scene_{scene_num}: {type(exc).__name__}: {exc}"
                ) from exc

            assets.append(
                ImageAsset(
                    scene_number=scene_num,
                    image_path=str(image_path),
                    prompt=full_prompt,
                    seed=-1,
                )
            )

        return assets

    def _compose_image_prompt(self, *, subject: str, scene_prompt: str, overlay: object) -> str:
        overlay_text = str(overlay).strip() if isinstance(overlay, str) else ""
        prompt_parts = [scene_prompt.strip() or f"visual concept for {subject}"]
        if overlay_text and overlay_text.lower() not in scene_prompt.lower():
            prompt_parts.append(f"focus on {overlay_text.lower()}")
        if subject and subject.lower() not in scene_prompt.lower():
            prompt_parts.append(f"topic anchor {subject}")
        prompt_parts.extend(
            [
                "vertical 9:16 composition",
                "single cohesive visual idea",
                "cinematic lighting",
                "modern workplace realism",
                "no text",
                "no logo",
            ]
        )
        return ", ".join(self._dedupe_prompt_parts(prompt_parts))

    def _dedupe_prompt_parts(self, prompt_parts: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for part in prompt_parts:
            normalized = part.strip(" ,").lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(part.strip(" ,"))
        return deduped

    async def _generate_single_image(
        self,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "",
        seed: int = -1,
    ) -> None:
        cmd = [
            self.sd_cli_path,
            "-m", self.sd_model_path,
            "--clip_l", self.sd_clip_l_path,
            "--clip_g", self.sd_clip_g_path,
            "--t5xxl", self.sd_t5xxl_path,
            "-H", str(self.sd_height),
            "-W", str(self.sd_width),
            "-p", prompt,
            "-n", negative_prompt,
            "--cfg-scale", str(self.sd_cfg_scale),
            "--sampling-method", self.sd_sampling_method,
            "--clip-on-cpu",
            "--vae-on-cpu",
            "--seed", str(seed),
            "-o", str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"sd-cli failed: {result.stderr}")

    def _postprocess_generated_image(self, image_path: Path) -> None:
        """Force generated images to cover the target frame cleanly."""
        subprocess.run(
            [
                "convert",
                str(image_path),
                "-resize",
                f"{self.sd_width}x{self.sd_height}^",
                "-gravity",
                "center",
                "-extent",
                f"{self.sd_width}x{self.sd_height}",
                str(image_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def _create_scene_card(
        self,
        image_path: Path,
        title: str,
        prompt: str,
        overlay: str,
        style: str,
    ) -> None:
        image_path.parent.mkdir(parents=True, exist_ok=True)
        background = {
            "mock": "#1a1a1a",
            "local": "#101820",
            "fallback": "#2b1f17",
        }.get(style, "#101820")
        accent = {
            "mock": "#b8860b",
            "local": "#d4af37",
            "fallback": "#c46b2f",
        }.get(style, "#d4af37")

        safe_prompt = prompt.replace("'", "’")[:180]
        safe_overlay = overlay.replace("'", "’")[:60]
        label = f"{title}\n\n{safe_overlay}\n\n{safe_prompt}"

        subprocess.run(
            [
                "convert",
                "-size",
                f"{self.sd_width}x{self.sd_height}",
                f"xc:{background}",
                "-fill",
                accent,
                "-draw",
                f"rectangle 80,80 {self.sd_width - 80},{self.sd_height - 80}",
                "-fill",
                background,
                "-draw",
                f"rectangle 92,92 {self.sd_width - 92},{self.sd_height - 92}",
                "-fill",
                accent,
                "-gravity",
                "north",
                "-font",
                "DejaVu-Sans-Bold",
                "-pointsize",
                "56",
                "-annotate",
                "+0+180",
                title,
                "-font",
                "DejaVu-Sans",
                "-pointsize",
                "34",
                "-fill",
                "white",
                "-gravity",
                "center",
                "-annotate",
                "+0+0",
                label,
                "-fill",
                accent,
                "-gravity",
                "south",
                "-pointsize",
                "28",
                "-annotate",
                "+0+120",
                "Stoic Modernized",
                str(image_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def save_assets(self, assets: list[ImageAsset]) -> Path:
        from src.utils import save_json

        data = {
            "images": [a.model_dump() for a in assets],
            "generated_at": "generated-locally",
        }
        return save_json(data, self.images_dir / "assets.json")

    def load_assets(self) -> Optional[list[ImageAsset]]:
        from src.utils import load_json

        assets_path = self.images_dir / "assets.json"
        if not assets_path.exists():
            return None

        data = load_json(assets_path)
        return [ImageAsset(**a) for a in data.get("images", [])]
