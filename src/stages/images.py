"""Image generation stage module using stable diffusion CLI or local fallbacks."""

import json
import re
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import httpx

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
        self.sd_log_path = self.images_dir / "sd-cli.log"

        self.sd_cli_path = settings.sd_cli_path
        self.sd_model_path = settings.sd_model_path
        self.sd_clip_l_path = settings.sd_clip_l_path
        self.sd_clip_g_path = settings.sd_clip_g_path
        self.sd_t5xxl_path = settings.sd_t5xxl_path
        self.sd_width = settings.sd_image_width
        self.sd_height = settings.sd_image_height
        self.sd_cfg_scale = settings.sd_cfg_scale
        self.sd_steps = settings.sd_steps
        self.sd_sampling_method = settings.sd_sampling_method
        self.sd_negative_prompt = settings.sd_negative_prompt

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
        negative_prompt = self.sd_negative_prompt

        for scene in scene_plan.get("scenes", []):
            scene_num = scene["scene_number"]
            image_path = self.images_dir / f"scene_{scene_num:03d}.jpg"
            scene_prompt = scene.get("visual_prompt", "")
            full_prompt = await self._rewrite_image_prompt_with_local_llm(
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

    async def _rewrite_image_prompt_with_local_llm(self, *, subject: str, scene_prompt: str, overlay: object) -> str:
        fallback_prompt = self._compose_image_prompt(subject=subject, scene_prompt=scene_prompt, overlay=overlay)
        overlay_text = str(overlay).strip() if isinstance(overlay, str) else ""

        sanitized_scene_prompt = self._sanitize_scene_prompt(scene_prompt)
        prompt = f"""
Rewrite the following image concept into one clean natural-language prompt for Stable Diffusion 3.5 Large.

Video topic: {subject}
Scene concept: {sanitized_scene_prompt}
Overlay takeaway: {overlay_text or 'none'}

Requirements:
- Output exactly one natural-language image prompt line.
- Use descriptive, cinematic natural language, not comma spam.
- Keep it visually concrete and realistic.
- Prefer a single clear subject or focal action.
- Emphasize modern workplace realism when appropriate.
- Include vertical 9:16 composition naturally.
- Do not include phrases like 'no text', 'no logo', 'negative prompt', 'vertical 9:16 frame', 'frame', or 'border'.
- Do not mention Stable Diffusion, SDXL, model names, parameters, or camera metadata.
- Do not include lists, bullets, JSON, or extra commentary.
""".strip()

        payload = {
            "model": settings.local_image_prompt_model or settings.local_llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You rewrite image prompts into clean natural-language prompts. Return one prompt line only.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": settings.local_image_prompt_temperature,
            "max_tokens": settings.local_image_prompt_max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        try:
            async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
                response = await client.post(settings.local_llm_base_url, json=payload)
                response.raise_for_status()
            data = response.json()
            content = self._extract_message_content(data)
            cleaned = self._clean_llm_image_prompt(content)
            return cleaned or fallback_prompt
        except Exception:
            return fallback_prompt

    def _compose_image_prompt(self, *, subject: str, scene_prompt: str, overlay: object) -> str:
        overlay_text = str(overlay).strip() if isinstance(overlay, str) else ""
        base_scene = self._sanitize_scene_prompt(scene_prompt) or f"A visual concept for {subject}."
        sentences = [base_scene.rstrip(". ") + "."]
        if overlay_text and overlay_text.lower() not in base_scene.lower():
            sentences.append(f"The image should emphasize {overlay_text.lower()}.")
        if subject and subject.lower() not in base_scene.lower():
            sentences.append(f"Keep the scene clearly connected to the video topic: {subject}.")
        sentences.append(
            "Use a single clear subject, modern workplace realism, calm natural lighting, sharp focus, and a vertical 9:16 composition."
        )
        return " ".join(sentences)

    def _build_safe_retry_prompt(self, *, subject: str, scene_prompt: str, overlay: str) -> str:
        base_scene = self._sanitize_scene_prompt(scene_prompt) or f"A single focused worker in a modern office setting related to {subject}."
        simple_overlay = overlay.strip() if overlay else "the main task"
        return (
            f"{base_scene.rstrip('. ')}. "
            f"Show one clear focal subject and emphasize {simple_overlay.lower()}. "
            f"Modern minimalist office, clean organized desk, calm natural lighting, realistic editorial photography, vertical 9:16 composition."
        )

    def _build_safe_retry_negative_prompt(self) -> str:
        return "blurry, low quality, deformed, extra people, crowd, cluttered desk, chaos, text, logo, watermark, overexposed, burnt"

    def _sanitize_scene_prompt(self, scene_prompt: str) -> str:
        cleaned = scene_prompt or ""
        banned_phrases = [
            "vertical 9:16 frame",
            "vertical 9:16 composition",
            "no text",
            "no logo",
            "single cohesive visual idea",
            "cinematic lighting",
            "modern workplace realism",
            "gold accents",
            "dark refined palette",
            "dark elegant palette",
            "atmospheric lighting",
        ]
        lowered = cleaned.lower()
        for phrase in banned_phrases:
            lowered = lowered.replace(phrase, " ")
        lowered = re.sub(r"\s+", " ", lowered).strip(" ,.")
        if not lowered:
            return ""
        return lowered[0].upper() + lowered[1:]

    def _extract_message_content(self, data: dict) -> str:
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

    def _clean_llm_image_prompt(self, text: str) -> str:
        cleaned = (text or "").strip().strip('"').strip("'")
        cleaned = re.sub(r"\s+", " ", cleaned)
        banned = ["no text", "no logo", "negative prompt", "vertical 9:16 frame", "border", "frame"]
        lowered = cleaned.lower()
        if not cleaned or any(term in lowered for term in banned):
            return ""
        return cleaned

    async def _generate_single_image(
        self,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "",
        seed: int = -1,
    ) -> None:
        cmd = self._build_sd_command(
            prompt=prompt,
            output_path=output_path,
            negative_prompt=negative_prompt,
            seed=seed,
            cfg_scale=self.sd_cfg_scale,
            steps=self.sd_steps,
            sampling_method=self.sd_sampling_method,
        )

        result = subprocess.run(cmd, capture_output=True, text=True)
        self._append_sd_cli_log(output_path=output_path, command=cmd, result=result)
        if result.returncode == 0:
            return

        if self._is_sd_cli_assert_failure(result.stderr):
            retry_prompt = self._build_safe_retry_prompt(
                subject=self.job_dir.name,
                scene_prompt=prompt,
                overlay="focus",
            )
            retry_negative = self._build_safe_retry_negative_prompt()
            retry_cmd = self._build_sd_command(
                prompt=retry_prompt,
                output_path=output_path,
                negative_prompt=retry_negative,
                seed=seed,
                cfg_scale=4.0,
                steps=32,
                sampling_method="euler",
            )
            retry_result = subprocess.run(retry_cmd, capture_output=True, text=True)
            self._append_sd_cli_log(output_path=output_path, command=retry_cmd, result=retry_result)
            if retry_result.returncode == 0:
                return
            raise RuntimeError(
                f"sd-cli failed after safe retry: {retry_result.stderr or result.stderr}"
            )

        raise RuntimeError(f"sd-cli failed: {result.stderr}")

    def _build_sd_command(
        self,
        *,
        prompt: str,
        output_path: Path,
        negative_prompt: str,
        seed: int,
        cfg_scale: float,
        steps: int,
        sampling_method: str,
    ) -> list[str]:
        return [
            self.sd_cli_path,
            "-m", self.sd_model_path,
            "--clip_l", self.sd_clip_l_path,
            "--clip_g", self.sd_clip_g_path,
            "--t5xxl", self.sd_t5xxl_path,
            "-H", str(self.sd_height),
            "-W", str(self.sd_width),
            "-p", prompt,
            "-n", negative_prompt,
            "--cfg-scale", str(cfg_scale),
            "--steps", str(steps),
            "--sampling-method", sampling_method,
            "--clip-on-cpu",
            "--vae-on-cpu",
            "--seed", str(seed),
            "-o", str(output_path),
        ]

    def _is_sd_cli_assert_failure(self, stderr: str) -> bool:
        lowered = (stderr or "").lower()
        return "ggml_assert" in lowered or "assert(i01" in lowered

    def _append_sd_cli_log(
        self,
        *,
        output_path: Path,
        command: list[str],
        result: subprocess.CompletedProcess[str],
    ) -> None:
        self.sd_log_path.parent.mkdir(parents=True, exist_ok=True)
        separator = "\n" + ("=" * 100) + "\n"
        command_text = shlex.join(command)
        entry = (
            f"{separator}"
            f"timestamp: {datetime.now(UTC).isoformat()}\n"
            f"output_image: {output_path}\n"
            f"return_code: {result.returncode}\n"
            f"command:\n{command_text}\n\n"
            f"stdout:\n{result.stdout or '<empty>'}\n\n"
            f"stderr:\n{result.stderr or '<empty>'}\n"
        )
        with self.sd_log_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)

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
