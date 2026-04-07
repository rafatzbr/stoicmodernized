"""Image generation stage module using stable diffusion CLI or local fallbacks."""

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


# Fixed style suffix: appended AFTER LLM generates scene line
STYLE_SUFFIX = "realistic office setting, soft daylight, clean desk, subtle background blur, editorial photo"

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
        
        # Prompt seed management for variety
        self.prompt_seed_path = Path(__file__).parent / "prompt_seed.json"

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

            # LLM generates scene line only
            scene_line = await self._rewrite_image_prompt_with_local_llm(
                subject=subject,
                scene_prompt=scene_prompt,
                overlay=scene.get("text_overlay"),
                mode=mode,
            )
            # Append fixed style suffix once
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
