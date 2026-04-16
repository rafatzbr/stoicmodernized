"""Image generation stage module using stable diffusion CLI, SD server, or local fallbacks."""

import base64
import json
import random
import re
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import httpx

from src.config import settings
from src.models import ImageAsset

# Predefined elements for random combination in prompt generation
PROFESSIONS = [
    "office professional",
    "knowledge worker",
    "creative professional",
    "software engineer",
    "project manager",
    "team lead",
    "consultant",
]

ACTIONS = [
    "seated at a tidy desk writing",
    "pausing with hands resting on keyboard",
    "reviewing handwritten notes",
    "organizing workspace",
    "focusing on a physical notebook",
    "taking a mindful break",
    "reflecting while looking at a journal",
]

LOCATIONS = [
    "in a modern workplace",
    "at their home office desk",
    "in a quiet co-working space",
    "at a minimalist desk setup",
    "in a calm office environment",
]

CONCRETE_OBJECTS = [
    "notebook, pen, keyboard, and coffee mug visible",
    "phone placed face-down beside laptop",
    "physical journal with handwritten notes",
    "small succulent plant on desk corner",
    "water bottle and minimal items",
    "stress ball in hand",
    "cup of tea with steam rising",
]

BACKGROUNDS = [
    "blurred office activity",
    "soft focus window view",
    "subtle blurred figures in distance",
    "minimal office background",
    "calm neutral office wall",
]

FOREGROUNDS = [
    "organized workspace with controlled details",
    "clear focus on subject and notebook",
    "calm centered expression",
    "relaxed shoulders and posture",
    "mindful attention to task",
]


class ImageGenerationError(RuntimeError):
    """Raised when real image generation fails."""


class SdServerImageGeneration:
    """Image generation using local SD server (Automatic1111 or ComfyUI)."""

    def __init__(self, job_id: str, mock: bool = False):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.job_dir = settings.jobs_dir / job_id
        self.images_dir = self.job_dir / "images"
        self.sd_server_url = settings.sd_server_url
        self.sd_server_api_path = settings.sd_server_api_path
        self.sd_server_timeout = settings.sd_server_timeout_seconds

        # Server-specific settings
        self.sd_width = settings.sd_image_width
        self.sd_height = settings.sd_image_height
        self.sd_cfg_scale = settings.sd_cfg_scale
        self.sd_steps = settings.sd_steps
        self.sd_negative_prompt = settings.sd_negative_prompt
        self.sd_sampling_method = settings.sd_sampling_method

        # Prompt seed management for variety
        self.prompt_seed_path = Path(__file__).parent / "prompt_seed.json"

    async def generate(self, scene_plan: dict) -> list[ImageAsset]:
        """Generate images using SD server API."""
        self.images_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._generate_placeholder_images(scene_plan, style="mock")

        if self._server_available():
            return await self._server_generate(scene_plan)

        raise ImageGenerationError(
            f"sd_server_unavailable: SD server at {self.sd_server_url} is not accessible; "
            "check that the server is running and configured correctly"
        )

    def _server_available(self) -> bool:
        """Check if SD server is available."""
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.sd_server_url}/sdapi/v1/options")
                return response.status_code == 200
        except Exception:
            return False

    def _resolve_seed(self, seed: int) -> int:
        """Resolve seed for SD server. Returns -1 for random, or the provided seed."""
        return seed if seed != -1 else -1

    def _choose_scene_mode(self, scene_num: int) -> str:
        """Cycle through scene modes for variety."""
        return SCENE_MODES[scene_num % len(SCENE_MODES)]

    def _get_prompt_seed(self) -> int:
        """Get and increment prompt seed for variety."""
        try:
            if self.prompt_seed_path.exists():
                with open(self.prompt_seed_path, "r") as f:
                    seed_data = json.load(f)
                seed = seed_data.get("seed", 0) + 1
                seed_data["seed"] = seed
                seed_data["last_used"] = datetime.now(UTC).isoformat()
                seed_data["history"].append({
                    "timestamp": datetime.now(UTC).isoformat(),
                    "seed": seed,
                })
                with open(self.prompt_seed_path, "w") as f:
                    json.dump(seed_data, f, indent=2)
                return seed
            else:
                # Initialize seed file
                seed_data = {"seed": 1, "last_used": None, "history": []}
                with open(self.prompt_seed_path, "w") as f:
                    json.dump(seed_data, f, indent=2)
                return 1
        except Exception:
            # Fallback to random seed
            return random.randint(1, 999999)

    def _set_random_seed(self):
        """Set Python random seed based on prompt seed for variety."""
        seed = self._get_prompt_seed()
        random.seed(seed)

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
        """Generate placeholder images (same as before)."""
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

    async def _server_generate(self, scene_plan: dict) -> list[ImageAsset]:
        """Generate images using SD server API."""
        assets = []
        subject = self._extract_subject(scene_plan)
        negative_prompt = self.sd_negative_prompt

        for scene in scene_plan.get("scenes", []):
            scene_num = scene["scene_number"]
            image_path = self.images_dir / f"scene_{scene_num:03d}.jpg"
            scene_prompt = scene.get("visual_prompt", "")
            mode = self._choose_scene_mode(scene_num)

            # Use desk-scene specific negative prompt for object/hands/desk modes
            if mode in ["object_only", "hands_only", "over_shoulder"]:
                scene_negative_prompt = DESK_NEGATIVE_PROMPT
            else:
                scene_negative_prompt = negative_prompt

            # Set random seed for this scene to ensure variety
            self._set_random_seed()

            scene_line = build_narrative_scene_prompt(
                subject=subject,
                scene_prompt=scene_prompt,
                narration_segment=scene.get("narration_segment", ""),
                overlay=scene.get("text_overlay"),
                mode=mode,
            )
            full_prompt = f"{scene_line}, {STYLE_SUFFIX}"

            seed = self._resolve_seed(-1)
            try:
                await self._generate_single_image_from_server(
                    prompt=full_prompt,
                    output_path=image_path,
                    negative_prompt=scene_negative_prompt,
                    seed=seed,
                )
            except Exception as exc:
                raise ImageGenerationError(
                    f"image_generation_failed_for_scene_{scene_num}: {type(exc).__name__}: {exc}"
                ) from exc

            assets.append(
                ImageAsset(
                    scene_number=scene_num,
                    image_path=str(image_path),
                    prompt=full_prompt,
                    seed=seed,
                )
            )

        return assets

    async def _generate_single_image_from_server(
        self,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "",
        seed: int = -1,
    ) -> None:
        """Generate single image using SD server API."""
        # SD server API payload (Automatic1111 format, works with ComfyUI too)
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": self.sd_steps,
            "cfg_scale": self.sd_cfg_scale,
            "width": self.sd_width,
            "height": self.sd_height,
            "samples": 1,
            "batch_size": 1,
            "seed": seed if seed != -1 else -1,  # -1 = random
            "sampler_name": self.sd_sampling_method,
            "restore_faces": False,
            "tiling": False,
            "enable_hr": False,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with httpx.AsyncClient(timeout=self.sd_server_timeout) as client:
                response = await client.post(
                    f"{self.sd_server_url}{self.sd_server_api_path}",
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()

                # Extract image from response (base64 encoded)
                if "images" in result and result["images"]:
                    # First image is the one we want
                    image_data = result["images"][0]
                    if isinstance(image_data, str):
                        # Base64 string with optional header
                        if "," in image_data:
                            image_data = image_data.split(",", 1)[1]

                        # Decode base64 and save
                        image_bytes = base64.b64decode(image_data)
                        with open(output_path, "wb") as f:
                            f.write(image_bytes)
                    elif isinstance(image_data, dict) and "image" in image_data:
                        image_bytes = base64.b64decode(image_data["image"])
                        with open(output_path, "wb") as f:
                            f.write(image_bytes)
                    else:
                        raise ImageGenerationError(
                            f"Unexpected image format in response: {type(image_data)}"
                        )
                else:
                    raise ImageGenerationError(
                        f"SD server returned no images: {result}"
                    )

        except httpx.HTTPStatusError as e:
            raise ImageGenerationError(f"SD server HTTP error: {e.response.status_code} - {e.response.text}")
        except httpx.TimeoutException:
            raise ImageGenerationError(f"SD server request timed out after {self.sd_server_timeout}s")
        except httpx.RequestError as e:
            raise ImageGenerationError(f"SD server connection error: {e}")

    # Reuse the same helper methods from ImageGenerationStage
    def _mode_instruction(self, mode: str) -> str:
        """Return strict mode framing instruction."""
        instructions = {
            "object_only": "Show desk objects only. No person, no face, no hands unless required by the action.",
            "hands_only": "Show hands only. No face, no full person.",
            "over_shoulder": "Show one person from behind or over the shoulder. No eye contact.",
            "environment": "Show the workspace environment with minimal or no person visible.",
            "person_medium": "Show one person at a desk, upper body visible, not looking at camera.",
        }
        return instructions.get(mode, "Show one person at a desk, upper body visible, not looking at camera.")

    async def _rewrite_image_prompt_with_local_llm(
        self, *, subject: str, scene_prompt: str, overlay: object, mode: str
    ) -> str:
        """Same as in ImageGenerationStage but uses SD server settings."""
        # Translate abstract takeaways to concrete physical actions FIRST
        concrete_takeaway = self._translate_takeaway_to_concrete(overlay)
        sanitized_scene_prompt = self._sanitize_scene_prompt(scene_prompt)
        mode_instruction = self._mode_instruction(mode)

        # Use the new base prompt structure with random element expansion
        profession = random.choice(PROFESSIONS)
        action = random.choice(ACTIONS)
        location = random.choice(LOCATIONS)
        objects = random.choice(CONCRETE_OBJECTS)
        background = random.choice(BACKGROUNDS)
        foreground = random.choice(FOREGROUNDS)

        # Log for debugging
        self._log_prompt_debug(f"Random elements: {profession}, {action}, {location}, {objects}, {background}, {foreground}")

        expanded = f"""Subject: {subject}

A {profession} {action} {location}.
{objects}.
{background}.
{foreground}.

Channel: Stoic Modernized
Style: candid editorial photography, medium shot, slightly off-center, shallow depth of field, realistic skin texture, 35mm or 50mm lens, vertical 9:16
Lighting: soft natural window light

Now refine this into a detailed image prompt based on the topic: {subject}
Scene intent: {sanitized_scene_prompt}
Takeaway action: {concrete_takeaway}
Shot mode: {mode_instruction}

Write a detailed image prompt that expands on the above. Include all visual details.

CRITICAL: Do NOT use abstract words like "focus", "calm", "control", "pause", "mindful", "symbolizing", "concept". Describe only what can be photographed."""

        payload = {
            "model": settings.local_image_prompt_model or settings.local_llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": """You are an image prompt engineer for Stoic Modernized YouTube channel.

CRITICAL RULES:
1. Describe ONLY what can be photographed: visible people, actions, objects, lighting
2. NEVER use abstract words: focus, calm, control, pause, mindful, symbolic, concept, symbolizing, intentional, deliberate
3. NEVER explain meaning: don't say "symbolizing prepared actions" or "capturing the concept"
4. Use strong, concrete verbs: sliding, setting, placing, resting, writing, holding
5. Output ONLY the prompt text, no explanations, no thinking, no meta-commentary

BAD examples (NEVER do this):
- "focusing on the concept of control"
- "symbolizing prepared actions"
- "capturing the mindful moment"

GOOD examples (DO this):
- "hand sliding smartphone face-down beside laptop"
- "hands resting on keyboard, one holding pen"
- "open notebook with handwritten text beside laptop"""
                },
                {"role": "user", "content": expanded},
            ],
            "max_tokens": settings.local_image_prompt_max_tokens,
            "temperature": 0.3,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        try:
            self._log_prompt_debug(f"EXPANDED PROMPT: {expanded[:200]}...")

            max_retries = 5
            attempt = 0
            last_content = None

            while attempt < max_retries:
                async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
                    response = await client.post(settings.local_llm_base_url, json=payload)
                    response.raise_for_status()
                data = response.json()
                content = self._extract_message_content(data)

                self._log_prompt_debug(f"ATTEMPT {attempt + 1}: {content[:200] if content else 'EMPTY'}...")

                cleaned, is_valid, reason = self._sanitize_prompt(content)

                if cleaned and is_valid:
                    self._log_prompt(content, cleaned, "ok")
                    return cleaned

                self._log_prompt(content, cleaned, f"failed:{reason}")
                last_content = content

                if attempt < max_retries - 1:
                    attempt += 1
                    payload["messages"][1]["content"] = (
                        f"{expanded}\n\nRETRY: The previous attempt failed validation. "
                        f"Write a VALID image prompt that:\n"
                        f"- Contains NO banned words (focus, calm, control, pause, etc.)\n"
                        f"- Is 20-45 words\n"
                        f"- Describes ONLY visible objects and actions\n"
                        f"- Uses ONLY concrete, photographable details\n"
                        f"- Output ONLY the prompt text, nothing else."
                    )
                    payload["temperature"] = 0.2
            else:
                self._log_prompt_debug(f"ALL {max_retries} RETRIES FAILED")
                if last_content:
                    cleaned, _, _ = self._sanitize_prompt(last_content)
                    if cleaned:
                        self._log_prompt(last_content, cleaned, "best-effort")
                        return cleaned
                return self._build_safe_fallback_prompt(mode, subject)
        except Exception as e:
            self._log_prompt("", "", f"exception:{type(e).__name__}")
            return self._build_safe_fallback_prompt(mode, subject)

    def _translate_takeaway_to_concrete(self, overlay: object) -> str:
        """Translate abstract takeaway into concrete physical action/prop."""
        if not overlay:
            return "none"
        overlay_lower = str(overlay).strip().lower()
        for abstract, concrete in TAKEAWAY_MAP.items():
            if abstract in overlay_lower:
                return concrete
        return overlay.strip()

    def _sanitize_prompt(self, text: str) -> tuple[str, bool, str]:
        """Sanitize LLM output (same as ImageGenerationStage)."""
        if not text:
            return "", False, "empty"

        text = re.sub(r"\s+", " ", text).strip()

        sorted_banned = sorted(ABSTRACT_BAN_LIST, key=len, reverse=True)
        for banned in sorted_banned:
            text = re.sub(rf"\b{re.escape(banned)}\b", "", text, flags=re.IGNORECASE)

        meta_patterns = [
            r"Show one clear focal subject emphasizing.*",
            r"vertical 9:16",
            r"frame.*9:16",
            r"composition.*9:16",
            r"camera.*metadata",
            r"negative prompt",
            r"stable diffusion",
            r"json",
            r"bullet",
            r"list",
        ]
        for pattern in meta_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        awkward_patterns = [
            r"contrast between [^,]+,",
            r"place context:[^,]+,",
            r"workplace context:[^,]+,",
            r"simple [^,]+,",
            r"clear [^,]+,",
        ]
        for pattern in awkward_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        broken_phrases = [
            r'\b\w+ focusing on\b',
            r'\bcapturing the\b',
            r'\bsymbolizing [^.,]+',
            r'\brepresenting [^.,]+',
            r'\bshowing the\b',
        ]
        for pattern in broken_phrases:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        text = text.rstrip(".,")
        text = re.sub(r"\s{2,}", " ", text).strip()
        text = re.sub(r",\s*,", ",", text)
        text = re.sub(r"[.,]+\s*", ".", text)
        text = text.strip(".")

        text_lower = text.lower()
        banned_found = []
        for banned in ABSTRACT_BAN_LIST:
            if banned.lower() in text_lower:
                banned_found.append(banned)
        if banned_found:
            return text, False, f"banned:{','.join(banned_found[:3])}"

        style_found = []
        for fragment in STYLE_FRAGMENT_FRAGMENTS:
            if fragment.lower() in text_lower:
                style_found.append(fragment)
        if style_found:
            return text, False, f"style_leak:{','.join(style_found[:2])}"

        word_count = len(text.split())
        if word_count < 20 or word_count > 45:
            return text, False, f"word_count:{word_count}"

        for verb in WEAK_VERBS:
            if verb.lower() in text_lower:
                return text, False, f"weak_verb:{verb}"

        object_count = 0
        for obj in ["laptop", "phone", "smartphone", "notebook", "desk", "keyboard", "mug", "pen"]:
            object_count += len(re.findall(rf"\b{obj}\b", text_lower))
        if object_count > 4:
            return text, False, f"too_many_objects:{object_count}"

        return text, True, "ok"

    def _build_safe_fallback_prompt(self, mode: str, topic: str = "") -> str:
        """Build a safe fallback prompt (same as ImageGenerationStage)."""
        topic_lower = (topic or "").lower()
        for keyword, fallback in TOPIC_FALLBACKS.items():
            if keyword in topic_lower:
                return fallback
        return ULTRA_SAFE_FALLBACK

    def _log_prompt(self, raw: str, cleaned: str, status: str):
        """Log LLM prompt processing for debugging."""
        log_path = self.images_dir / "llm_prompt_debug.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"STATUS: {status}\n")
                f.write(f"RAW: {raw[:500] if raw else 'EMPTY'}\n")
                f.write(f"CLEANED: {cleaned[:500] if cleaned else 'EMPTY'}\n")
        except Exception:
            pass

    def _log_prompt_debug(self, message: str):
        """Log debug messages for prompt generation."""
        log_path = self.images_dir / "llm_prompt_debug.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[DEBUG] {message}\n")
        except Exception:
            pass

    def _extract_message_content(self, data: dict) -> str:
        """Extract message content from LLM response."""
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

    def _sanitize_scene_prompt(self, scene_prompt: str) -> str:
        """Sanitize scene prompt (same as ImageGenerationStage)."""
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

    def _create_scene_card(
        self,
        image_path: Path,
        title: str,
        prompt: str,
        overlay: str,
        style: str,
    ) -> None:
        """Create a scene card image (same as ImageGenerationStage)."""
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

        safe_prompt = prompt.replace("'", "•")[:180]
        safe_overlay = overlay.replace("'", "•")[:60]
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
        """Save assets to JSON (same as ImageGenerationStage)."""
        from src.utils import save_json

        data = {
            "images": [a.model_dump() for a in assets],
            "generated_at": "generated-from-server",
        }
        return save_json(data, self.images_dir / "assets.json")

    def load_assets(self) -> Optional[list[ImageAsset]]:
        """Load assets from JSON (same as ImageGenerationStage)."""
        from src.utils import load_json

        assets_path = self.images_dir / "assets.json"
        if not assets_path.exists():
            return None

        data = load_json(assets_path)
        return [ImageAsset(**a) for a in data.get("images", [])]



# Fixed style suffix: appended AFTER LLM generates scene line
STYLE_SUFFIX = "natural office photography, candid editorial realism, soft window light, realistic skin, vertical 9:16"

BOUNDARY_SCENE_TEMPLATES = {
    "pause first": {
        "object_only": "Smartphone turned face-down beside an open laptop and a small notebook on a tidy work desk, unread notifications glowing faintly on a second monitor in the background, natural office details, no person visible",
        "hands_only": "Close view of hands at a work desk, one hand turning a smartphone face-down beside an open laptop, the other hand resting near a notebook and pen, notification glow softly blurred in the background",
        "over_shoulder": "Over-the-shoulder view of a worker at a desk, phone turned face-down beside laptop before replying, inbox and chat notifications softly blurred on the monitor, notebook and pen ready beside the keyboard",
        "environment": "Modern office workspace with a chair pulled in toward a desk, phone face-down beside laptop, notebook and pen arranged neatly, Slack or email notifications glowing softly on a distant monitor, subtle office movement blurred behind",
        "person_medium": "Office worker seated at a desk, looking at a laptop while setting a smartphone face-down beside the keyboard, notebook and pen visible, unread notifications softly blurred on a second monitor, upper body visible, slightly off-center",
    },
    "what you control": {
        "object_only": "Open laptop beside a notebook divided into two simple columns, pen laid across the page, phone set aside at the edge of the desk, blurred office activity in the background, clean modern workspace",
        "hands_only": "Hands writing in a notebook beside an open laptop, one short column of personal tasks visible, phone face-down at the edge of the desk, blurred office movement in the distance",
        "over_shoulder": "Over-the-shoulder view of a worker writing in a notebook beside an open laptop, one page showing a short personal task list while office activity stays blurred in the background, phone set aside near the keyboard",
        "environment": "Organized desk in a modern office with an open laptop, notebook, pen, and phone set aside, background coworkers and movement softly blurred to contrast with the ordered foreground",
        "person_medium": "Worker at a desk writing in a notebook beside an open laptop, phone set aside, foreground organized and still while office movement stays softly blurred behind, upper body visible, not looking at camera",
    },
    "after the meeting": {
        "object_only": "Laptop open on a quiet desk after a meeting, notebook with a few bullet points, pen resting across the page, empty conference chairs blurred in the background, warm office light",
        "hands_only": "Hands writing a few bullet points in a notebook beside an open laptop after a meeting, coffee cup and conference room glass wall blurred in the background",
        "over_shoulder": "Over-the-shoulder view of a worker alone at a desk after a meeting, writing notes beside an open laptop while empty conference chairs and a glass wall sit softly blurred behind",
        "environment": "Quiet office desk after a meeting, laptop open, notebook with pen, abandoned conference room blurred in the background, warm evening office light, no person visible",
        "person_medium": "Worker alone at a desk after a meeting, writing in a notebook beside an open laptop, empty conference room chairs softly blurred behind, tired office atmosphere but composed posture, upper body visible",
    },
    "use this today": {
        "object_only": "Closed laptop, notebook, badge, and shoulder bag arranged on a tidy desk near the end of the workday, office lights warm in the background, modern workplace details",
        "hands_only": "Hands closing a laptop and reaching for a shoulder bag beside a notebook on a tidy work desk, end-of-day office light, no face visible",
        "over_shoulder": "Over-the-shoulder view of a worker closing a laptop and standing up from a desk, notebook and bag visible, office lights warm in the background, no eye contact",
        "environment": "Modern office workspace at the end of the day, laptop closed, notebook and bag ready to leave, hallway lights warm and slightly blurred in the background, no person visible",
        "person_medium": "Office worker standing from a desk after closing a laptop, notebook and bag visible, end-of-day office light, upper body visible, slightly off-center, leaving on time rather than staying late",
    },
}


def _normalize_scene_key(overlay: object, scene_prompt: str, narration_segment: str) -> str | None:
    combined = " ".join(
        part.strip().lower() for part in [str(overlay or ""), scene_prompt or "", narration_segment or ""] if str(part).strip()
    )
    for key in BOUNDARY_SCENE_TEMPLATES:
        if key in combined:
            return key
    return None


def _generic_mode_prompt(mode: str, subject: str, narration_segment: str) -> str:
    lowered = f"{subject} {narration_segment}".lower()
    if any(word in lowered for word in ["boundary", "boundaries", "fired", "burnout", "overcommit", "overcommitting"]):
        if mode == "object_only":
            return "Open laptop, notebook, and phone face-down on a tidy office desk, unread chat notifications softly blurred in the background, modern workplace details, no person visible"
        if mode == "hands_only":
            return "Hands at a work desk, one hand moving a phone away from the keyboard while the other rests near an open notebook and laptop, close framing, no face visible"
        if mode == "over_shoulder":
            return "Over-the-shoulder view of a worker at a desk, notebook open beside a laptop, phone set aside, blurred chat notifications and office activity in the background"
        if mode == "environment":
            return "Organized office workspace with laptop, notebook, and phone set aside in the foreground, office movement softly blurred behind, modern workplace lighting, no person visible"
        return "Worker at a desk with notebook open beside a laptop, phone set aside instead of in hand, upper body visible, slightly off-center, office activity softly blurred in the background"

    if mode == "object_only":
        return "Open laptop, notebook, pen, and coffee mug on a tidy modern desk, realistic workplace details, no person visible"
    if mode == "hands_only":
        return "Hands writing in a notebook beside an open laptop on a modern desk, close framing, no face visible"
    if mode == "over_shoulder":
        return "Over-the-shoulder view of a worker at a desk with laptop and notebook visible, realistic office details, no eye contact"
    if mode == "environment":
        return "Modern office workspace with organized desk in the foreground and softly blurred background activity, no person visible"
    return "Office worker seated at a desk with laptop and notebook visible, upper body framed slightly off-center, realistic workplace details"


def build_narrative_scene_prompt(
    *,
    subject: str,
    scene_prompt: str,
    narration_segment: str,
    overlay: object,
    mode: str,
) -> str:
    scene_key = _normalize_scene_key(overlay, scene_prompt, narration_segment)
    if scene_key:
        return BOUNDARY_SCENE_TEMPLATES[scene_key].get(mode, BOUNDARY_SCENE_TEMPLATES[scene_key]["person_medium"])
    return _generic_mode_prompt(mode, subject, narration_segment)

# Scene modes for variety
SCENE_MODES = ["object_only", "hands_only", "over_shoulder", "environment", "person_medium"]

# Hard-banned abstract words in LLM output
ABSTRACT_BAN_LIST = [
    # Abstract emotional/philosophical concepts
    "calm", "focus", "control", "urgency", "burnout", "stoicism", "discipline",
    "emotional", "symbolic", "mindful", "grounded", "prepared", "meditative",
    "zen", "serene", "centered", "balanced", "intentional", "deliberate",
    "external noise", "what you control", "pause", "respond", "discipline",
    "return", "returning", "stopping", "distraction", "silence", "intentionally",
    # Text-rendering details (SD3.5 struggles with text)
    # NOTE: "note" alone is banned but "notebook" is allowed
    "handwritten", "written", "checklist", "text on page", "one next step",
    "next step", "task list", "checkboxes", "marked", "checked off",
    # Temporal action phrases
    "hovers", "briefly", "about to", "pausing before", "returning to",
    "before", "after", "while", "as", "during",
    # Decorative details
    "steaming mug", "wood grain", "matte finish", "polished oak", "texture",
    "grain", "smooth", "glossy", "reflective", "shiny", "detailed texture",
]

# Weak/muddy verbs to avoid in prompts
WEAK_VERBS = ["hovering", "pausing", "returning", "preparing", "emphasizing"]

# Style suffix fragments that should not appear in LLM output (will be appended in Python)
STYLE_FRAGMENT_FRAGMENTS = [
    "realistic office setting",
    "soft daylight",
    "clean desk",
    "subtle background blur",
    "editorial photo",
]

# Desk-scene specific negative prompt
DESK_NEGATIVE_PROMPT = (
    "blurry, low quality, deformed, cluttered desk, text, logo, watermark, "
    "overexposed, bad hands, awkward hand pose, extra hands, extra fingers, "
    "missing fingers, duplicate objects, distorted phone, malformed laptop, "
    "illegible writing, plastic texture, oversmoothed surfaces"
)

# Translate abstract takeaways into concrete physical actions/objects
TAKEAWAY_MAP = {
    "pause before responding": "hand placing phone face-down beside keyboard",
    "focus on what you control": "notebook beside open laptop",
    "stop doomscrolling": "smartphone placed face-down and moved away from workspace",
    "discipline over mood": "pen beside notebook at tidy desk",
    "respond intentionally": "hand placing phone face-down beside keyboard",
    "one next task": "notebook beside open laptop",
    "breathe before acting": "hand above keyboard",
    "control the impulse": "laptop closed, notebook open",
    "silence the noise": "smartphone face-down",
    "return to the work": "notebook open, phone face-down",
}

# Topic-specific fallback templates (preferred prompts for recurring topics)
TOPIC_FALLBACKS = {
    "doomscroll": "Close-up of a hand sliding a smartphone face-down away from an open laptop on a tidy office desk, with a notebook nearby",
    "doomscrolling": "Close-up of a hand sliding a smartphone face-down away from an open laptop on a tidy office desk, with a notebook nearby",
    "pause before responding": "Close-up of a hand setting a smartphone face-down beside an open laptop on a tidy office desk",
    "pause": "Close-up of a hand setting a smartphone face-down beside an open laptop on a tidy office desk",
    "focus on what you control": "Open laptop and notebook on a tidy office desk, smartphone set aside nearby",
    "control": "Open laptop and notebook on a tidy office desk, smartphone set aside nearby",
    "boundaries": "Smartphone placed face-down at the edge of a tidy office desk beside an open laptop",
    "protect attention": "Smartphone placed face-down at the edge of a tidy office desk beside an open laptop",
    "one task at a time": "Close-up of a hand near an open laptop and notebook on a clean office desk",
}

# Ultra-safe final fallback (fallback for fallbacks)
ULTRA_SAFE_FALLBACK = "A smartphone face-down beside an open laptop on a tidy office desk, realistic office, soft daylight"


class ImageGenerationStage:
    """Handles image generation for scenes using SD CLI, SD Server, or fallbacks."""

    def __init__(self, job_id: str, mock: bool = False, placeholder_only: bool = False):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.placeholder_only = placeholder_only or settings.force_placeholder_images
        self.job_dir = settings.jobs_dir / job_id
        self.images_dir = self.job_dir / "images"
        self.sd_log_path = self.images_dir / "sd-cli.log"

        # SD CLI settings
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

        # SD Server settings
        self.sd_server_url = settings.sd_server_url
        self.sd_server_api_path = settings.sd_server_api_path
        self.sd_server_timeout = settings.sd_server_timeout_seconds

        # Prompt seed management for variety
        self.prompt_seed_path = Path(__file__).parent / "prompt_seed.json"

    async def run(self, scene_plan: dict) -> list[ImageAsset]:
        """Run image generation stage."""
        self.images_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._generate_placeholder_images(scene_plan, style="mock")

        if self.placeholder_only:
            return await self._generate_placeholder_images(scene_plan, style="local")

        # Priority: SD Server > SD CLI > Error
        if self._sd_server_available():
            sd_gen = SdServerImageGeneration(self.job_id, mock=False)
            return await sd_gen.generate(scene_plan)

        if self._sd_cli_available():
            return await self._real_generate(scene_plan)

        # Determine error message based on what's missing
        if not self._sd_cli_available():
            if not self._sd_server_available():
                raise ImageGenerationError(
                    "no_image_provider_available: "
                    "neither SD CLI nor SD server is available; "
                    "use --placeholder-images for local generated cards, "
                    "or set up SD CLI or SD server"
                )
            raise ImageGenerationError(
                "sd_cli_unavailable: stable diffusion CLI or model files are missing; "
                "use --placeholder-images if you want local placeholder cards"
            )

    def _sd_cli_available(self) -> bool:
        return Path(self.sd_cli_path).exists() and Path(self.sd_model_path).exists()

    def _sd_server_available(self) -> bool:
        """Check if SD server is available."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.sd_server_url}/sdapi/v1/options")
                return response.status_code == 200
        except Exception:
            return False

    def _resolve_seed(self, seed: int) -> int:
        """Resolve seed for sd-cli. Returns -1 for random, or the provided seed."""
        return seed if seed != -1 else -1

    def _choose_scene_mode(self, scene_num: int) -> str:
        """Cycle through scene modes for variety."""
        return SCENE_MODES[scene_num % len(SCENE_MODES)]

    def _get_prompt_seed(self) -> int:
        """Get and increment prompt seed for variety."""
        try:
            if self.prompt_seed_path.exists():
                with open(self.prompt_seed_path, "r") as f:
                    seed_data = json.load(f)
                seed = seed_data.get("seed", 0) + 1
                seed_data["seed"] = seed
                seed_data["last_used"] = datetime.now(UTC).isoformat()
                seed_data["history"].append({
                    "timestamp": datetime.now(UTC).isoformat(),
                    "seed": seed,
                })
                with open(self.prompt_seed_path, "w") as f:
                    json.dump(seed_data, f, indent=2)
                return seed
            else:
                # Initialize seed file
                seed_data = {"seed": 1, "last_used": None, "history": []}
                with open(self.prompt_seed_path, "w") as f:
                    json.dump(seed_data, f, indent=2)
                return 1
        except Exception:
            # Fallback to random seed
            return random.randint(1, 999999)

    def _set_random_seed(self):
        """Set Python random seed based on prompt seed for variety."""
        seed = self._get_prompt_seed()
        random.seed(seed)

    def _mode_instruction(self, mode: str) -> str:
        """Return strict mode framing instruction."""
        instructions = {
            "object_only": "Show desk objects only. No person, no face, no hands unless required by the action.",
            "hands_only": "Show hands only. No face, no full person.",
            "over_shoulder": "Show one person from behind or over the shoulder. No eye contact.",
            "environment": "Show the workspace environment with minimal or no person visible.",
            "person_medium": "Show one person at a desk, upper body visible, not looking at camera.",
        }
        return instructions.get(mode, "Show one person at a desk, upper body visible, not looking at camera.")

    def _extract_subject(self, scene_plan: dict) -> str:
        topic = scene_plan.get("topic") if isinstance(scene_plan, dict) else None
        if isinstance(topic, str) and topic.strip():
            return topic.strip()

        scenes = scene_plan.get("scenes", []) if isinstance(scene_plan, dict) else []
        for scene in scenes:
            if not isinstance.scene(scene, dict):
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
            mode = self._choose_scene_mode(scene_num)

            # Use desk-scene specific negative prompt for object/hands/desk modes
            if mode in ["object_only", "hands_only", "over_shoulder"]:
                scene_negative_prompt = DESK_NEGATIVE_PROMPT
            else:
                scene_negative_prompt = negative_prompt

            # Set random seed for this scene to ensure variety
            self._set_random_seed()

            scene_line = build_narrative_scene_prompt(
                subject=subject,
                scene_prompt=scene_prompt,
                narration_segment=scene.get("narration_segment", ""),
                overlay=scene.get("text_overlay"),
                mode=mode,
            )
            full_prompt = f"{scene_line}, {STYLE_SUFFIX}"

            seed = self._resolve_seed(-1)
            try:
                await self._generate_single_image(
                    prompt=full_prompt,
                    output_path=image_path,
                    negative_prompt=scene_negative_prompt,
                    seed=seed,
                    subject=subject,
                    scene_prompt=scene_prompt,
                    overlay=scene.get("text_overlay"),
                    mode=mode,
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
                    seed=seed,
                )
            )

        return assets

    def _translate_takeaway_to_concrete(self, overlay: object) -> str:
        """Translate abstract takeaway into concrete physical action/prop."""
        if not overlay:
            return "none"
        overlay_lower = str(overlay).strip().lower()
        for abstract, concrete in TAKEAWAY_MAP.items():
            if abstract in overlay_lower:
                return concrete
        return overlay.strip()

    def _sanitize_prompt(self, text: str) -> tuple[str, bool, str]:
        """Sanitize LLM output: strip banned phrases, enforce structure, ensure quality.
        
        Returns:
            (sanitized_prompt, is_valid, reason)
        - is_valid: True if prompt passed all checks
        - reason: Why it was rejected (or "ok" if valid)
        """
        if not text:
            return "", False, "empty"
        
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        
        # Remove banned abstract words (longer phrases first)
        sorted_banned = sorted(ABSTRACT_BAN_LIST, key=len, reverse=True)
        for banned in sorted_banned:
            text = re.sub(rf"\b{re.escape(banned)}\b", "", text, flags=re.IGNORECASE)
        
        # Remove meta-instructions
        meta_patterns = [
            r"Show one clear focal subject emphasizing.*",
            r"vertical 9:16",
            r"frame.*9:16",
            r"composition.*9:16",
            r"camera.*metadata",
            r"negative prompt",
            r"stable diffusion",
            r"json",
            r"bullet",
            r"list",
        ]
        for pattern in meta_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        
        # Remove awkward remnants
        awkward_patterns = [
            r"contrast between [^,]+,",
            r"place context:[^,]+,",
            r"workplace context:[^,]+,",
            r"simple [^,]+,",
            r"clear [^,]+,",
        ]
        for pattern in awkward_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        
        # Clean up broken phrases from word removal (e.g., "focusing on" -> "on")
        broken_phrases = [
            r'\b\w+ focusing on\b',  # "focusing on" or "focuses on"
            r'\bcapturing the\b',     # "capturing the concept"
            r'\bsymbolizing [^.,]+',  # "symbolizing prepared actions"
            r'\brepresenting [^.,]+', # "representing control"
            r'\bshowing the\b',       # "showing the concept"
        ]
        for pattern in broken_phrases:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        
        # Remove trailing punctuation
        text = text.rstrip(".,")
        
        # Clean up double spaces and punctuation junk
        text = re.sub(r"\s{2,}", " ", text).strip()
        text = re.sub(r",\s*,", ",", text)  # Remove duplicated commas
        text = re.sub(r"[.,]+\s*", ".", text)  # Clean trailing punctuation
        text = text.strip(".")
        
        # Check 1: Still contains banned words?
        text_lower = text.lower()
        banned_found = []
        for banned in ABSTRACT_BAN_LIST:
            if banned.lower() in text_lower:
                banned_found.append(banned)
        if banned_found:
            return text, False, f"banned:{','.join(banned_found[:3])}"
        
        # Check 2: Contains style fragments (should be appended in Python)?
        style_found = []
        for fragment in STYLE_FRAGMENT_FRAGMENTS:
            if fragment.lower() in text_lower:
                style_found.append(fragment)
        if style_found:
            return text, False, f"style_leak:{','.join(style_found[:2])}"
        
        # Check 3: Word count (20-45 words)?
        word_count = len(text.split())
        if word_count < 20 or word_count > 45:
            return text, False, f"word_count:{word_count}"
        
        # Check 4: Contains weak verbs?
        for verb in WEAK_VERBS:
            if verb.lower() in text_lower:
                return text, False, f"weak_verb:{verb}"
        
        # Check 5: Too many objects/actions? (simplified check)
        # Count primary objects: laptop, phone, smartphone, notebook, desk, keyboard, mug, pen
        object_count = 0
        for obj in ["laptop", "smartphone", "phone", "notebook", "desk", "keyboard", "mug", "pen"]:
            object_count += len(re.findall(rf"\b{obj}\b", text_lower))
        if object_count > 4:
            return text, False, f"too_many_objects:{object_count}"
        
        return text, True, "ok"

    def _build_safe_fallback_prompt(self, mode: str, topic: str = "") -> str:
        """Build a safe fallback prompt if LLM output is malformed.
        
        Priority:
        1. Topic-specific fallback
        2. Ultra-safe fallback
        3. Mode-specific safe default
        """
        # 1. Topic-specific fallbacks first
        topic_lower = (topic or "").lower()
        for keyword, fallback in TOPIC_FALLBACKS.items():
            if keyword in topic_lower:
                return fallback
        
        # 2. Ultra-safe fallback
        return ULTRA_SAFE_FALLBACK

    async def _rewrite_image_prompt_with_local_llm(
        self, *, subject: str, scene_prompt: str, overlay: object, mode: str
    ) -> str:
        # Translate abstract takeaways to concrete physical actions FIRST
        concrete_takeaway = self._translate_takeaway_to_concrete(overlay)
        sanitized_scene_prompt = self._sanitize_scene_prompt(scene_prompt)
        mode_instruction = self._mode_instruction(mode)

        # Use the new base prompt structure with random element expansion
        # This ensures variety while maintaining channel identity
        profession = random.choice(PROFESSIONS)
        action = random.choice(ACTIONS)
        location = random.choice(LOCATIONS)
        objects = random.choice(CONCRETE_OBJECTS)
        background = random.choice(BACKGROUNDS)
        foreground = random.choice(FOREGROUNDS)
        
        # Log for debugging
        self._log_prompt_debug(f"Random elements: {profession}, {action}, {location}, {objects}, {background}, {foreground}")

        expanded = f"""Subject: {subject}

A {profession} {action} {location}.
{objects}.
{background}.
{foreground}.

Channel: Stoic Modernized
Style: candid editorial photography, medium shot, slightly off-center, shallow depth of field, realistic skin texture, 35mm or 50mm lens, vertical 9:16
Lighting: soft natural window light

Now refine this into a detailed image prompt based on the topic: {subject}
Scene intent: {sanitized_scene_prompt}
Takeaway action: {concrete_takeaway}
Shot mode: {mode_instruction}

Write a detailed image prompt that expands on the above. Include all visual details.

CRITICAL: Do NOT use abstract words like "focus", "calm", "control", "pause", "mindful", "symbolizing", "concept". Describe only what can be photographed."""

        payload = {
            "model": settings.local_image_prompt_model or settings.local_llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": """You are an image prompt engineer for Stoic Modernized YouTube channel.

CRITICAL RULES:
1. Describe ONLY what can be photographed: visible people, actions, objects, lighting
2. NEVER use abstract words: focus, calm, control, pause, mindful, symbolic, concept, symbolizing, intentional, deliberate
3. NEVER explain meaning: don't say "symbolizing prepared actions" or "capturing the concept"
4. Use strong, concrete verbs: sliding, setting, placing, resting, writing, holding
5. Output ONLY the prompt text, no explanations, no thinking, no meta-commentary

BAD examples (NEVER do this):
- "focusing on the concept of control"
- "symbolizing prepared actions"
- "capturing the mindful moment"

GOOD examples (DO this):
- "hand sliding smartphone face-down beside laptop"
- "hands resting on keyboard, one holding pen"
- "open notebook with handwritten text beside laptop"""
                },
                {"role": "user", "content": expanded},
            ],
            "max_tokens": settings.local_image_prompt_max_tokens,
            "temperature": 0.3,  # Lower temperature for more deterministic output
            "chat_template_kwargs": {"enable_thinking": False},
        }

        try:
            # Log the expanded prompt for debugging
            self._log_prompt_debug(f"EXPANDED PROMPT: {expanded[:200]}...")
            
            # Retry up to 5 times to get a valid prompt
            max_retries = 5
            attempt = 0
            last_content = None
            
            while attempt < max_retries:
                async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
                    response = await client.post(settings.local_llm_base_url, json=payload)
                    response.raise_for_status()
                data = response.json()
                content = self._extract_message_content(data)
                
                # Log what the LLM returned
                self._log_prompt_debug(f"ATTEMPT {attempt + 1}: {content[:200] if content else 'EMPTY'}...")
                
                # Sanitize output
                cleaned, is_valid, reason = self._sanitize_prompt(content)
                
                # Check validation
                if cleaned and is_valid:
                    self._log_prompt(content, cleaned, "ok")
                    return cleaned
                
                # Log failure and prepare for retry
                self._log_prompt(content, cleaned, f"failed:{reason}")
                last_content = content
                
                if attempt < max_retries - 1:
                    # Increment attempt counter and try again with modified prompt
                    attempt += 1
                    # Make the prompt more specific and add retry instruction
                    payload["messages"][1]["content"] = (
                        f"{expanded}\n\nRETRY: The previous attempt failed validation. "
                        f"Write a VALID image prompt that:\n"
                        f"- Contains NO banned words (focus, calm, control, pause, etc.)\n"
                        f"- Is 20-45 words\n"
                        f"- Describes ONLY visible objects and actions\n"
                        f"- Uses ONLY concrete, photographable details\n"
                        f"- Output ONLY the prompt text, nothing else."
                    )
                    # Lower temperature on retries for more deterministic output
                    payload["temperature"] = 0.2
            else:
                # All retries failed
                self._log_prompt_debug(f"ALL {max_retries} RETRIES FAILED")
                # Return last cleaned content even if invalid (fallback is too generic)
                if last_content:
                    cleaned, _, _ = self._sanitize_prompt(last_content)
                    if cleaned:
                        self._log_prompt(last_content, cleaned, "best-effort")
                        return cleaned
                
                # Ultimate fallback
                return self._build_safe_fallback_prompt(mode, subject)
        except Exception as e:
            self._log_prompt("", "", f"exception:{type(e).__name__}")
            return self._build_safe_fallback_prompt(mode, subject)

    def _log_prompt(self, raw: str, cleaned: str, status: str):
        """Log LLM prompt processing for debugging."""
        log_path = self.images_dir / "llm_prompt_debug.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"STATUS: {status}\n")
                f.write(f"RAW: {raw[:500] if raw else 'EMPTY'}\n")
                f.write(f"CLEANED: {cleaned[:500] if cleaned else 'EMPTY'}\n")
        except Exception:
            pass  # Don't fail on debug logging

    def _log_prompt_debug(self, message: str):
        """Log debug messages for prompt generation."""
        log_path = self.images_dir / "llm_prompt_debug.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[DEBUG] {message}\n")
        except Exception:
            pass  # Don't fail on debug logging

    def _compose_image_prompt(
        self, *, subject: str, scene_prompt: str, overlay: object, mode: str
    ) -> str:
        """Compose prompt following Rafael's guidance: subject/action + props + composition + environment.
        
        Key principles:
        - Concrete visible objects/actions, NOT abstract ideas
        - ONE clear action (not mixed like "hands only" + "torso")
        - Specific desk props that match the topic
        - Clean composition, no style manifesto spam
        """
        overlay_text = str(overlay).strip() if isinstance(overlay, str) else ""
        base_scene = self._sanitize_scene_prompt(scene_prompt) or self._default_for_mode(mode)

        # Translate abstract overlay into ONE concrete visual action/prop
        visual_action = self._translate_to_concrete_action(overlay_text, mode)

        sentences = []

        # Start with the core scene/action
        if visual_action:
            sentences.append(f"{base_scene}. {visual_action}.")
        else:
            sentences.append(f"{base_scene}.")

        # Add composition and environment (minimal, no manifesto)
        sentences.append(f"{self._composition_for_mode(mode)}, vertical 9:16, editorial realism.")

        return " ".join(sentences)

    def _default_for_mode(self, mode: str) -> str:
        """Default scene description for each mode.
        
        Keep it simple: subject/action + props + environment
        """
        defaults = {
            "object_only": "Clean modern office desk with notebook, pen, coffee mug, and smartphone face-down beside keyboard. Soft daylight, realistic textures.",
            "hands_only": "Hands at clean office desk, one writing in notebook, one resting near laptop. Relaxed posture, soft window light.",
            "over_shoulder": "Over-the-shoulder view at tidy desk, open laptop visible, notebook with handwritten text, smartphone face-down. Soft daylight.",
            "environment": "Modern office with organized desk in foreground, softly blurred activity in background. Calm workspace, natural light.",
            "person_medium": "Professional at tidy desk in modern office, upper body visible, slightly off-center, writing in notebook. Soft daylight.",
        }
        return defaults.get(mode, "Professional at tidy desk in modern office.")

    def _translate_to_concrete_action(
        self, overlay: str, mode: str
    ) -> str:
        """Translate abstract overlay into ONE concrete visible action/prop.
        
        Key principle: The model needs a photographable act, not meaning.
        For "stop doomscrolling," the act is: put phone down, turn it over, return to one task.
        """
        if not overlay:
            return ""

        overlay_lower = overlay.lower()

        # Theme: stop doomscrolling / digital distraction
        if any(term in overlay_lower for term in ["doomscroll", "phone", "distraction", "mute", "silence"]):
            return "smartphone placed face-down beside keyboard"

        # Theme: calm / control / prepared
        if any(term in overlay_lower for term in ["calm", "control", "prepared", "focus", "discipline"]):
            return "handwriting one task on checklist"

        # Theme: pause / breathe / respond
        if any(term in overlay_lower for term in ["pause", "breathe", "respond", "thinks", "thinking"]):
            return "pausing before typing, hand hovering over keyboard"

        # Theme: boundaries / boundaries
        if any(term in overlay_lower for term in ["boundary", "solitude", "alone", "isolated"]):
            return "one person at desk, quiet office"

        # Theme: persistence / grind / endurance
        if any(term in overlay_lower for term in ["persistence", "grind", "endurance", "patience"]):
            return "notebook with multiple completed tasks checked off"

        # Default: tidy desk with focused action
        return "tidy desk with notebook and pen"

    def _composition_for_mode(self, mode: str) -> str:
        """Return minimal composition instruction for each mode."""
        compositions = {
            "object_only": "close-up of objects on desk, no people",
            "hands_only": "close-up of hands only, desk surface visible",
            "over_shoulder": "over-the-shoulder view, screen blurred in background",
            "environment": "medium shot, calm workspace in foreground, office softly blurred behind",
            "person_medium": "medium shot, upper body visible, slightly off-center",
        }
        return compositions.get(mode, "medium shot at desk")

    def _build_safe_retry_prompt(
        self, *, subject: str, scene_prompt: str, overlay: str, mode: str
    ) -> str:
        """Simpler retry prompt."""
        base = self._sanitize_scene_prompt(scene_prompt) or self._default_for_mode(mode)
        simple_overlay = overlay.strip() if overlay else "the main task"
        return f"{base}. Show one clear focal subject emphasizing {simple_overlay.lower()}. Vertical 9:16."

    def _build_safe_retry_negative_prompt(self) -> str:
        """Negative prompt per Rafael's guidance (2026-04-05)."""
        return (
            "blurry, low quality, deformed, extra people, cluttered desk, text, logo, watermark, "
            "overexposed, bad hands, extra fingers, missing fingers, duplicate objects, malformed laptop, "
            "distorted phone, distorted pen, plastic skin, uncanny face, centered portrait, "
            "stock photo pose, oversmoothed skin, staged smile, direct eye contact"
        )

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
        """Strip/normalize whitespace, reject meta outputs, allow 18–90 words."""
        cleaned = (text or "").strip().strip('"').strip("'")
        cleaned = re.sub(r"\s+", " ", cleaned)
        lowered = cleaned.lower()

        # Reject meta outputs
        banned = [
            "negative prompt",
            "stable diffusion",
            "sdxl",
            "json",
            "bullet",
            "list",
            "camera metadata",
            "no text",
            "no logo",
        ]
        if not cleaned or any(term in lowered for term in banned):
            return ""

        # Word count: allow 18–90 words
        word_count = len(cleaned.split())
        if word_count < 18 or word_count > 90:
            return ""

        return cleaned

    async def _generate_single_image(
        self,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "",
        seed: int = -1,
        subject: str = "",
        scene_prompt: str = "",
        overlay: object = None,
        mode: str = "person_medium",
    ) -> None:
        resolved_seed = self._resolve_seed(seed)

        cmd = self._build_sd_command(
            prompt=prompt,
            output_path=output_path,
            negative_prompt=negative_prompt,
            seed=resolved_seed,
            cfg_scale=self.sd_cfg_scale,
            steps=self.sd_steps,
            sampling_method=self.sd_sampling_method,
        )

        attempt_id = self._append_sd_cli_log_start(output_path=output_path, command=cmd)
        result = subprocess.run(cmd, capture_output=True, text=True)
        self._append_sd_cli_log_result(attempt_id=attempt_id, result=result)
        if result.returncode == 0:
            return

        if self._is_sd_cli_assert_failure(result.stderr):
            retry_prompt = self._build_safe_retry_prompt(
                subject=subject,
                scene_prompt=scene_prompt or prompt,
                overlay=str(overlay).strip() if isinstance(overlay, str) else "focus",
                mode=mode,
            )
            retry_negative = self._build_safe_retry_negative_prompt()
            retry_cmd = self._build_sd_command(
                prompt=retry_prompt,
                output_path=output_path,
                negative_prompt=retry_negative,
                seed=resolved_seed,
                cfg_scale=4.0,
                steps=32,
                sampling_method="euler",
            )
            retry_attempt_id = self._append_sd_cli_log_start(output_path=output_path, command=retry_cmd)
            retry_result = subprocess.run(retry_cmd, capture_output=True, text=True)
            self._append_sd_cli_log_result(attempt_id=retry_attempt_id, result=retry_result)
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
            "--diffusion-model", "/data/sd-models/flux1-schnell-q8_0.gguf",
            "--clip_l", self.sd_clip_l_path,
            "--t5xxl", self.sd_t5xxl_path,
            "--vae", "/data/sd-models/ae.safetensors",
            "-H", str(self.sd_height),
            "-W", str(self.sd_width),
            "-p", prompt,
            "-n", negative_prompt,
            "--cfg-scale", str(cfg_scale),
            "--steps", str(steps),
            "--sampling-method", sampling_method,
            "--seed", str(seed),
            "-o", str(output_path),
        ]

    def _is_sd_cli_assert_failure(self, stderr: str) -> bool:
        lowered = (stderr or "").lower()
        return "ggml_assert" in lowered or "assert(i01" in lowered

    def _append_sd_cli_log_start(self, *, output_path: Path, command: list[str]) -> str:
        self.sd_log_path.parent.mkdir(parents=True, exist_ok=True)
        separator = "\n" + ("=" * 100) + "\n"
        command_text = shlex.join(command)
        attempt_id = f"{datetime.now(UTC).isoformat()}::{output_path.name}"
        entry = (
            f"{separator}"
            f"attempt_id: {attempt_id}\n"
            f"timestamp: {datetime.now(UTC).isoformat()}\n"
            f"output_image: {output_path}\n"
            f"command:\n{command_text}\n\n"
            f"status: started\n"
        )
        with self.sd_log_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        return attempt_id

    def _append_sd_cli_log_result(
        self,
        *,
        attempt_id: str,
        result: subprocess.CompletedProcess[str],
    ) -> None:
        entry = (
            f"return_code: {result.returncode}\n"
            f"stdout:\n{result.stdout or '<empty>'}\n\n"
            f"stderr:\n{result.stderr or '<empty>'}\n"
            f"status: finished ({attempt_id})\n"
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
