"""Text-to-speech stage module."""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
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

    def _edge_tts_command_prefix(self) -> list[str]:
        """Return an Edge TTS invocation bound to the active Python env when possible.

        Some hosts have a stale ~/.local/bin/edge-tts wrapper with a hard-coded
        /usr/bin/python3 shebang while the package is installed in the project
        virtualenv. Prefer `sys.executable -m edge_tts` so the CLI uses the same
        interpreter that is running this pipeline.
        """
        if importlib.util.find_spec("edge_tts") is not None:
            return [sys.executable, "-m", "edge_tts"]
        binary = shutil.which("edge-tts")
        if not binary:
            raise RuntimeError("edge-tts is not installed or not on PATH")
        return [binary]

    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rate_percent = int(round((self.speed - 1.0) * 100))
        rate = f"{rate_percent:+d}%"

        cmd = [
            *self._edge_tts_command_prefix(),
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


class KokoroTTSAudio(TTSAudioInterface):
    """Audio-only Kokoro TTS provider using a configured local CLI."""

    name = "kokoro"

    def __init__(
        self,
        command: str = "kokoro-tts",
        voice: str = "af_sarah",
        speed: float = 1.0,
        timeout_seconds: float = 300.0,
        model_path: Optional[Path] = None,
        voices_path: Optional[Path] = None,
        language: str = "en-gb",
    ):
        self.command = command
        self.voice = voice
        self.speed = speed
        self.timeout_seconds = timeout_seconds
        self.model_path = model_path
        self.voices_path = voices_path
        self.language = language

    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        _ = kwargs
        direct_error: Optional[Exception] = None
        if self._can_render_with_kokoro_onnx():
            try:
                return self._generate_with_kokoro_onnx(text, output_path)
            except Exception as e:
                direct_error = e

        binary = shutil.which(self.command)
        if not binary:
            if direct_error is not None:
                raise RuntimeError(
                    "kokoro-onnx direct renderer failed and "
                    f"{self.command} is not installed or not on PATH"
                ) from direct_error
            raise RuntimeError(f"{self.command} is not installed or not on PATH")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            binary,
            "--text",
            text,
            "--output",
            str(output_path),
            "--voice",
            self.voice,
            "--speed",
            f"{self.speed:g}",
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=self.timeout_seconds)
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="replace") if e.stderr else str(e)
            raise RuntimeError(f"kokoro-tts failed: {stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("kokoro-tts timed out") from e

        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise RuntimeError("kokoro-tts did not produce a non-empty audio file")

        return output_path

    def _can_render_with_kokoro_onnx(self) -> bool:
        return bool(
            self.model_path
            and self.voices_path
            and Path(self.model_path).exists()
            and Path(self.voices_path).exists()
        )

    def _generate_with_kokoro_onnx(self, text: str, output_path: Path) -> Path:
        try:
            import soundfile as sf
            from kokoro_onnx import Kokoro
        except Exception as e:
            raise RuntimeError("kokoro-onnx direct renderer dependencies are not installed") from e

        output_path.parent.mkdir(parents=True, exist_ok=True)
        kokoro = Kokoro(str(self.model_path), str(self.voices_path))
        samples, sample_rate = kokoro.create(
            text,
            voice=self.voice,
            speed=self.speed,
            lang=self.language,
        )
        sf.write(output_path, samples, sample_rate)

        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise RuntimeError("kokoro-onnx did not produce a non-empty audio file")
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
        self.provider = self._normalize_provider(provider or settings.tts_provider.value)
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

    def _normalize_provider(self, provider: str) -> str:
        normalized_provider = provider.strip().lower()
        aliases = {
            "edge": "edge",
            "edge-tts": "edge",
            "kokoro": "kokoro",
            "kokoro-tts": "kokoro",
        }
        if normalized_provider not in aliases:
            raise RuntimeError(
                f"Unsupported TTS provider '{provider}'. Supported providers: edge, kokoro."
            )
        return aliases[normalized_provider]

    async def run(self, scene_plan: dict) -> Path:
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        if self.mock:
            raise RuntimeError("Mock/local TTS has been removed. Use a real configured TTS provider.")

        audio_extension = settings.kokoro_format if self.provider == "kokoro" else "mp3"
        audio_path = self.audio_dir / f"narration.{audio_extension.lstrip('.')}"
        subtitles_path = self.audio_dir / "narration.vtt"

        # Extract narration from scene plan
        narration_segments = [
            scene.get("narration_segment", "")
            for scene in scene_plan.get("scenes", [])
            if scene.get("narration_segment")
            and scene.get("narration_segment") not in {"Intro branding", "Outro branding"}
        ]
        all_text = " ".join(narration_segments).strip() or "Stoic Modernized"

        audio_interface = self._audio_interface()

        try:
            if self.provider == "edge":
                return await audio_interface.generate_audio(
                    all_text,
                    audio_path,
                    subtitles_path=subtitles_path,
                )
            generated_path = await audio_interface.generate_audio(all_text, audio_path)
            await self._write_edge_subtitle_template(all_text)
            return generated_path
        except Exception as e:
            print(f"[TTS] {self.provider} generation failed: {e}")
            raise RuntimeError(f"TTS generation failed for provider '{self.provider}'.") from e

    async def _write_edge_subtitle_template(self, text: str) -> None:
        """Write an EdgeTTS VTT sidecar for cue structure when using audio-only TTS.

        Kokoro has no native subtitle sidecar. We keep Kokoro audio, but ask
        EdgeTTS to emit its familiar phrase cue structure into a separate VTT
        template that the subtitle stage can retime against Kokoro alignment.
        Failure is non-fatal: forced alignment/ASR fallbacks still work.
        """

        if not settings.tts_subtitles_enabled:
            return
        template_vtt = self.audio_dir / "narration.edge.vtt"
        template_audio = self.audio_dir / "narration.edge-template.mp3"
        try:
            await EdgeTTSAudio(voice=self.voice, speed=settings.tts_speed).generate_audio(
                text,
                template_audio,
                subtitles_path=template_vtt,
            )
        except Exception as exc:
            print(f"[TTS] Edge subtitle template generation skipped: {exc}")
        finally:
            try:
                if template_audio.exists():
                    template_audio.unlink()
            except Exception:
                pass

    def _audio_interface(self) -> TTSAudioInterface:
        if self.provider == "kokoro":
            return KokoroTTSAudio(
                command=settings.kokoro_command,
                voice=settings.kokoro_voice,
                speed=settings.kokoro_speed if settings.kokoro_speed is not None else settings.tts_speed,
                timeout_seconds=settings.kokoro_timeout_seconds,
                model_path=settings.kokoro_model_path,
                voices_path=settings.kokoro_voices_path,
                language=settings.kokoro_language,
            )
        return EdgeTTSAudio(voice=self.voice, speed=settings.tts_speed)
