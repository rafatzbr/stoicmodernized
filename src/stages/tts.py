"""Text-to-speech stage module using Edge TTS only."""

import json
import re
import subprocess
from pathlib import Path
from typing import Optional

from src.config import Channel, settings
from src.utils import load_json


class TTSAudioInterface:
    """Base interface for TTS providers."""

    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        """Generate audio from text."""
        raise NotImplementedError


class EdgeTTSAudio(TTSAudioInterface):
    """Edge TTS provider using the installed edge-tts CLI."""

    name = "edge"

    def __init__(self, voice: str = "en-US-GuyNeural", speed: float = 1.0):
        self.voice = voice
        self.speed = speed

    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        import shutil

        binary = shutil.which("edge-tts")
        if not binary:
            raise RuntimeError("edge-tts is not installed or not on PATH")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        rate_percent = int(round((self.speed - 1.0) * 100))
        rate = f"{rate_percent:+d}%"

        cmd = [
            binary,
            "--voice",
            kwargs.get("voice", self.voice),
            "--rate",
            rate,
            "--text",
            text,
            "--write-media",
            str(output_path),
        ]

        subtitles_path = kwargs.get("subtitles_path")
        if subtitles_path:
            cmd.extend(["--write-subtitles", str(subtitles_path)])

        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"edge-tts failed: {e.stderr.decode()}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("edge-tts timed out")

        return output_path


class TTSStage:
    """Handles TTS generation."""

    def __init__(
        self,
        job_id: str,
        provider: str = "edge",
        mock: bool = False,
        channel: Optional[Channel] = None,
    ):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        normalized_provider = (provider or settings.tts_provider.value).strip().lower()
        if normalized_provider not in {"edge", "edge-tts"}:
            raise RuntimeError(f"Unsupported TTS provider '{provider}'. Only edge-tts is enabled.")
        self.provider = "edge"
        self.job_dir = settings.jobs_dir / job_id
        self.audio_dir = self.job_dir / "audio"
        self.channel = channel or self._resolve_channel_from_job()
        self.voice = settings.get_channel_tts_voice(self.channel)

    def save_audio_path(self, audio_path: Path) -> None:
        """Save the audio path to the job metadata."""
        from src.utils import save_json

        job_data_path = self.job_dir / "job.json"
        if job_data_path.exists():
            job_data = load_json(job_data_path)
            job_data["audio_path"] = str(audio_path)
            save_json(job_data, job_data_path)

    def _resolve_channel_from_job(self) -> Channel:
        job_data_path = self.job_dir / "job.json"
        if job_data_path.exists():
            try:
                data = load_json(job_data_path)
                return Channel(data.get("channel", settings.default_channel.value))
            except Exception:
                return settings.default_channel
        return settings.default_channel

    async def run(self, scene_plan: dict) -> Path:
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        if self.mock:
            raise RuntimeError("Mock/local TTS has been removed. Use edge-tts.")

        audio_path = self.audio_dir / "narration.mp3"
        subtitles_path = self.audio_dir / "narration.vtt"

        # Extract narration from scene plan
        narration_segments = [
            scene.get("narration_segment", "")
            for scene in scene_plan.get("scenes", [])
            if scene.get("narration_segment")
            and scene.get("narration_segment") not in {"Intro branding", "Outro branding"}
        ]
        all_text = " ".join(narration_segments).strip() or "Stoic Modernized"

        audio_interface = EdgeTTSAudio(voice=self.voice, speed=settings.tts_speed)

        try:
            return await audio_interface.generate_audio(
                all_text,
                audio_path,
                subtitles_path=subtitles_path,
            )
        except Exception as e:
            print(f"[TTS] Edge generation failed: {e}")
            raise RuntimeError("TTS generation failed for provider 'edge'.") from e
