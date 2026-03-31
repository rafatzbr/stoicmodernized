"""Text-to-speech stage module with pluggable providers."""

import math
import struct
import wave
from pathlib import Path
from typing import Optional

from src.config import settings


class TTSAudioInterface:
    """Base interface for TTS providers."""

    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        """Generate audio from text."""
        raise NotImplementedError


class LocalTTSAudio(TTSAudioInterface):
    """Local fallback TTS provider.

    This implementation intentionally avoids requiring heavyweight local TTS
    engines. Instead, it creates a real WAV narration track made of paced tones
    and short silences so downstream stages have actual media assets to work
    with in local/non-mock mode.
    """

    name = "local"

    def __init__(self, voice: str = "adam", speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        self.sample_rate = 22050
        self.amplitude = 12000

    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        """Generate a real WAV file usable by the render pipeline."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        segments = self._split_text(text)
        with wave.open(str(output_path), "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)

            for index, segment in enumerate(segments):
                frequency = 220 + (index % 7) * 40
                duration = self._segment_duration(segment)
                wav_file.writeframes(self._tone_bytes(frequency, duration))
                wav_file.writeframes(self._silence_bytes(0.08))

        return output_path

    def _split_text(self, text: str) -> list[str]:
        chunks = [chunk.strip() for chunk in text.replace("\n", " ").split(".") if chunk.strip()]
        return chunks or [text.strip() or "Stoic Modernized"]

    def _segment_duration(self, text: str) -> float:
        words = max(1, len(text.split()))
        base_seconds = words / max(0.5, 2.6 * self.speed)
        return max(0.35, min(base_seconds, 8.0))

    def _tone_bytes(self, frequency: float, duration: float) -> bytes:
        frame_count = int(self.sample_rate * duration)
        frames = bytearray()
        fade_frames = max(1, min(frame_count // 10, int(self.sample_rate * 0.03)))

        for i in range(frame_count):
            envelope = 1.0
            if i < fade_frames:
                envelope = i / fade_frames
            elif i > frame_count - fade_frames:
                envelope = max(0.0, (frame_count - i) / fade_frames)

            sample = int(
                self.amplitude
                * envelope
                * math.sin(2 * math.pi * frequency * (i / self.sample_rate))
            )
            frames.extend(struct.pack("<h", sample))

        return bytes(frames)

    def _silence_bytes(self, duration: float) -> bytes:
        frame_count = int(self.sample_rate * duration)
        return b"\x00\x00" * frame_count


class ElevenLabsTTSAudio(TTSAudioInterface):
    """ElevenLabs TTS provider."""

    name = "elevenlabs"

    def __init__(self, api_key: Optional[str] = None, voice: str = "Adam"):
        self.api_key = api_key or settings.tts_api_key
        self.voice = voice
        self.base_url = "https://api.elevenlabs.io/v1"

    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        if not self.api_key:
            raise RuntimeError(
                "ElevenLabs API key not configured. Set TTS_API_KEY environment variable."
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        voice_id = await self._get_voice_id(self.voice)

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

            with open(output_path, "wb") as output_file:
                output_file.write(response.content)

        return output_path

    async def _get_voice_id(self, voice_name: str) -> str:
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
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.provider = provider
        self.job_dir = settings.jobs_dir / job_id
        self.audio_dir = self.job_dir / "audio"

        if provider == "elevenlabs":
            self.audio_interface: TTSAudioInterface = ElevenLabsTTSAudio()
        else:
            self.audio_interface = LocalTTSAudio(
                voice=settings.tts_voice, speed=settings.tts_speed
            )

    async def run(self, scene_plan: dict) -> Path:
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = self.audio_dir / "narration.wav"

        narration_segments = [
            scene.get("narration_segment", "")
            for scene in scene_plan.get("scenes", [])
            if scene.get("narration_segment")
            and scene.get("narration_segment") not in {"Intro branding", "Outro branding"}
        ]
        all_text = " ".join(narration_segments).strip() or "Stoic Modernized"

        if self.mock:
            return await LocalTTSAudio(voice=settings.tts_voice, speed=settings.tts_speed).generate_audio(
                all_text, audio_path
            )

        if self.provider == "elevenlabs" and not settings.tts_api_key:
            self.audio_interface = LocalTTSAudio(
                voice=settings.tts_voice, speed=settings.tts_speed
            )

        return await self.audio_interface.generate_audio(all_text, audio_path)

    def save_audio_path(self, audio_path: Path) -> None:
        from src.database import db

        db.update_job(self.job_id, status="tts_complete", audio_path=str(audio_path))

    def load_audio_path(self) -> Optional[str]:
        from src.database import db

        job = db.get_job(self.job_id)
        return job.audio_path if job else None
