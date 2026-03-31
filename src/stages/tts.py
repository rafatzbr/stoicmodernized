"""Text-to-speech stage module with pluggable providers."""

import subprocess
from pathlib import Path
from typing import Optional

from src.config import settings
from src.models import JobStatus


class TTSAudioInterface:
    """Base interface for TTS providers."""

    async def generate_audio(
        self, text: str, output_path: Path, **kwargs
    ) -> Path:
        """Generate audio from text.

        Args:
            text: Text to convert to speech
            output_path: Path for output audio file
            **kwargs: Provider-specific options

        Returns:
            Path to generated audio file
        """
        raise NotImplementedError


class LocalTTSAudio(TTSAudioInterface):
    """Local TTS provider (placeholder).

    This is a mock implementation. In production, you would integrate
    with a local TTS engine like:
    - Coqui TTS
    - Piper TTS
    - Edge-TTS (Microsoft)
    - pyttsx3 (offline, but limited voices)
    """

    name = "local"

    def __init__(self, voice: str = "adam", speed: float = 1.0):
        """Initialize local TTS.

        Args:
            voice: Voice name to use
            speed: Speech speed multiplier (1.0 = normal)
        """
        self.voice = voice
        self.speed = speed

    async def generate_audio(
        self, text: str, output_path: Path, **kwargs
    ) -> Path:
        """Generate mock audio file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # In production, this would call actual TTS engine
        # Example with Coqui TTS:
        # import torch
        # from TTS.api import TTS
        # tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        # tts.tts_to_file(text=text, file_path=str(output_path))

        # Mock: create empty file
        output_path.touch()

        return output_path


class ElevenLabsTTSAudio(TTSAudioInterface):
    """ElevenLabs TTS provider.

    Requires ELEVENLABS_API_KEY environment variable.
    """

    name = "elevenlabs"

    def __init__(self, api_key: Optional[str] = None, voice: str = "Adam"):
        """Initialize ElevenLabs TTS.

        Args:
            api_key: ElevenLabs API key (from env or settings)
            voice: Voice ID or name (default: Adam)
        """
        self.api_key = api_key or settings.tts_api_key
        self.voice = voice
        self.base_url = "https://api.elevenlabs.io/v1"

    async def generate_audio(
        self, text: str, output_path: Path, **kwargs
    ) -> Path:
        """Generate audio using ElevenLabs API.

        Args:
            text: Text to convert
            output_path: Output file path
            **kwargs: Additional options (model_id, stability, etc.)

        Returns:
            Path to generated audio file

        Raises:
            RuntimeError: If API key not configured
        """
        if not self.api_key:
            raise RuntimeError(
                "ElevenLabs API key not configured. "
                "Set ELEVENLABS_API_KEY environment variable."
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get voice ID from name
        voice_id = await self._get_voice_id(self.voice)

        # Call ElevenLabs API
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": kwargs.get("model_id", "eleven_monolingual_v1"),
                    "voice_settings": {
                        "stability": kwargs.get("stability", 0.5),
                        "similarity_boost": kwargs.get("similarity_boost", 0.75),
                    },
                },
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"ElevenLabs API error: {response.status_code} - {response.text}"
                )

            # Save audio
            with open(output_path, "wb") as f:
                f.write(response.content)

        return output_path

    async def _get_voice_id(self, voice_name: str) -> str:
        """Get voice ID from voice name.

        In production, this would query the ElevenLabs API.
        For now, return a hardcoded mapping.
        """
        voice_mapping = {
            "Adam": "pNInz6obpgDQGcFmaigg",
            "Rachel": "EXAVITQu4vr4xnSDxMaL",
            "Domi": "AZnzlk1XvdvUeBnXmlld",
            "Josh": "ErXwobaYiN019PkySvjV",
        }
        return voice_mapping.get(voice_name, "pNInz6obpgDQGcFmaigg")


class TTSStage:
    """Handles TTS generation stage."""

    def __init__(self, job_id: str, provider: str = "local", mock: bool = False):
        """Initialize TTS stage.

        Args:
            job_id: Unique job identifier
            provider: TTS provider ("local" or "elevenlabs")
            mock: If True, use mock data
        """
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.provider = provider
        self.job_dir = settings.jobs_dir / job_id
        self.audio_dir = self.job_dir / "audio"

        # Initialize audio interface
        if provider == "elevenlabs":
            self.audio_interface: TTSAudioInterface = ElevenLabsTTSAudio()
        else:
            self.audio_interface = LocalTTSAudio(
                voice=settings.tts_voice, speed=settings.tts_speed
            )

    async def run(self, scene_plan: dict) -> Path:
        """Generate TTS audio for all scenes.

        Args:
            scene_plan: Scene plan with narration segments

        Returns:
            Path to generated audio file
        """
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = self.audio_dir / "narration.wav"

        if self.mock:
            return await self._mock_generate(scene_plan, audio_path)

        if self.provider == "elevenlabs" and not settings.tts_api_key:
            # Fall back to local if no API key
            self.audio_interface = LocalTTSAudio()
            return await self._generate(scene_plan, audio_path)

        return await self._generate(scene_plan, audio_path)

    async def _mock_generate(self, scene_plan: dict, output_path: Path) -> Path:
        """Mock audio generation."""
        output_path.touch()
        return output_path

    async def _generate(self, scene_plan: dict, output_path: Path) -> Path:
        """Generate actual audio.

        TODO: Implement actual audio generation with real TTS provider
        """
        # Combine all narration segments
        all_text = " ".join(
            scene.get("narration_segment", "")
            for scene in scene_plan.get("scenes", [])
            if "narration_segment" in scene
        )

        # In production, generate audio here
        # For now, create mock file
        output_path.touch()

        return output_path

    def save_audio_path(self, audio_path: Path) -> None:
        """Save audio path to job record.

        Args:
            audio_path: Path to generated audio
        """
        from src.database import db

        db.update_job(self.job_id, status="tts_complete", audio_path=str(audio_path))

    def load_audio_path(self) -> Optional[str]:
        """Load audio path from job record.

        Returns:
            Audio path if exists, None otherwise
        """
        from src.database import db

        job = db.get_job(self.job_id)
        return job.audio_path if job else None
