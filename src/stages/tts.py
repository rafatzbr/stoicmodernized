"""Text-to-speech stage module with pluggable providers."""

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from typing import Optional

from src.config import settings


class TTSAudioInterface:
    """Base interface for TTS providers."""

    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        """Generate audio from text."""
        raise NotImplementedError


class VoxCPMTTS(TTSAudioInterface):
    """VoxCPM TTS provider - tokenizer-free multilingual speech synthesis via CLI.
    
    Uses VoxCPM.cpp which supports CPU, CUDA, and Vulkan backends.
    """

    name = "voxcpm"

    def __init__(
        self,
        model_path: str = None,
        voice: str = None,
        speed: float = 1.0,
        cfg_value: float = 2.0,
        inference_timesteps: int = 10,
        threads: int = 8,
        backend: str = "auto",
    ):
        """
        Initialize VoxCPM TTS.

        Args:
            model_path: Path to GGUF model file. If None, will look for default models.
            voice: Optional voice description for voice design (e.g., "calm, deep male voice")
            speed: Speech speed multiplier (0.25 to 4.0, default: 1.0)
                   Note: Speed control is NOT supported in VoxCPM.cpp CLI.
                   This parameter is stored but ignored. Use voice design for pace control.
            cfg_value: Guidance scale for generation (default: 2.0)
            inference_timesteps: Number of diffusion steps (default: 10)
            threads: Number of CPU threads to use (default: 8)
            backend: Backend to use: "cpu", "cuda", "vulkan", or "auto" (default: "auto")
        """
        self.model_path = model_path
        self.voice = voice
        self.speed = max(0.25, min(4.0, speed))
        self.cfg_value = cfg_value
        self.inference_timesteps = inference_timesteps
        self.threads = threads
        self.backend = backend
        self.sample_rate = 48000  # VoxCPM outputs 48kHz

        # Find the voxcpm CLI executable
        self._find_cli()

    def _find_cli(self):
        """Find the voxcpm TTS CLI executable."""
        import shutil
        import subprocess

        # Common locations for the voxcpm CLI
        possible_paths = [
            shutil.which("voxcpm_tts"),
            "./build/examples/voxcpm_tts",
            "./build-cuda/examples/voxcpm_tts",
            "/home/rafatz/dev/VoxCPM.cpp/build/examples/voxcpm_tts",
        ]

        for path in possible_paths:
            if path and Path(path).exists():
                self.cli_path = Path(path)
                return

        # Check if it's been built in the workspace
        voxcpm_cpp_dir = Path("/home/rafatz/dev/VoxCPM.cpp")
        if voxcpm_cpp_dir.exists():
            self.cli_path = voxcpm_cpp_dir / "build" / "examples" / "voxcpm_tts"
            if self.cli_path.exists():
                return

        raise RuntimeError(
            "VoxCPM.cpp CLI not found. Install and build VoxCPM.cpp:\n"
            "1. Clone: git clone https://github.com/bluryar/VoxCPM.cpp\n"
            "2. Build: cmake -B build && cmake --build build -j8\n"
            "3. Download model from: https://huggingface.co/bluryar/VoxCPM-GGUF"
        )

    def _get_model_path(self) -> Path:
        """Get the model path, downloading if necessary."""
        if self.model_path:
            model_path = Path(self.model_path)
            if not model_path.exists():
                raise RuntimeError(f"Model not found at: {model_path}")
            return model_path

        # Default model locations
        default_models = [
            Path("/home/rafatz/models/voxcpm/voxcpm1.5-q8_0-audiovae-f16.gguf"),
            Path("/home/rafatz/models/voxcpm/voxcpm-0.5b-q4_K.gguf"),
            Path("/data/voxcpm/voxcpm1.5-q8_0-audiovae-f16.gguf"),
        ]

        for model_path in default_models:
            if model_path.exists():
                print(f"Using VoxCPM model: {model_path}")
                return model_path

        # Try to find any voxcpm model
        model_dirs = [
            Path("/home/rafatz/models/voxcpm"),
            Path("/data/voxcpm"),
            Path("/home/rafatz/.cache/voxcpm"),
        ]

        for model_dir in model_dirs:
            if model_dir.exists():
                gguf_files = list(model_dir.glob("*.gguf"))
                if gguf_files:
                    model_path = gguf_files[0]
                    print(f"Found VoxCPM model: {model_path}")
                    return model_path

        raise RuntimeError(
            "No VoxCPM model found. Download from:\n"
            "https://huggingface.co/bluryar/VoxCPM-GGUF\n"
            "\nRecommended models:\n"
            "- voxcpm1.5-q8_0-audiovae-f16.gguf (942MB, balanced)\n"
            "- voxcpm-0.5b-q4_K.gguf (477MB, fastest)"
        )

    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        """Generate audio using the VoxCPM CLI."""
        import subprocess

        output_path.parent.mkdir(parents=True, exist_ok=True)

        model_path = self._get_model_path()

        # Prepare text with voice design if specified
        display_text = text
        if self.voice:
            display_text = f"({self.voice}) {text}"

        # Build the CLI command
        cmd = [
            str(self.cli_path),
            "--model-path",
            str(model_path),
            "--text",
            display_text,
            "--output",
            str(output_path),
            "--threads",
            str(self.threads),
            "--inference-timesteps",
            str(self.inference_timesteps),
            "--cfg-value",
            str(self.cfg_value),
        ]

        # Add backend
        if self.backend != "auto":
            cmd.extend(["--backend", self.backend])

        # Note: Speed control is NOT available in VoxCPM.cpp CLI.
        # Voice design descriptions can affect pace (e.g., "slightly slower pace")

        print(f"Generating audio with VoxCPM (backend: {self.backend})...")
        print(f"Command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes timeout
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise RuntimeError(f"VoxCPM CLI failed: {error_msg}")

            # Verify output was created
            if not output_path.exists():
                raise RuntimeError(f"VoxCPM CLI did not create output file: {output_path}")

            file_size = output_path.stat().st_size
            print(f"Audio generated: {output_path} ({file_size / 1024:.1f} KB)")
            return output_path

        except subprocess.TimeoutExpired:
            raise RuntimeError("VoxCPM generation timed out (10 minutes)")


class LocalTTSAudio(TTSAudioInterface):
    """Local fallback TTS provider."""

    name = "local"

    def __init__(self, voice: str = "adam", speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        self.sample_rate = 22050
        self.amplitude = 12000

    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
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


class EdgeTTSAudio(TTSAudioInterface):
    """Edge TTS provider using the installed edge-tts CLI."""

    name = "edge"

    def __init__(self, voice: str = "en-US-GuyNeural", speed: float = 1.0):
        self.voice = voice
        self.speed = speed

    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
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

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"edge-tts failed: {result.stderr.strip()}")

        return output_path


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
        self.audio_interface = self._build_interface(provider)

    def _build_interface(self, provider: str) -> TTSAudioInterface:
        if provider == "elevenlabs":
            return ElevenLabsTTSAudio()
        if provider in {"edge", "edge-tts"}:
            return EdgeTTSAudio(voice=settings.tts_voice, speed=settings.tts_speed)
        if provider == "voxcpm":
            return VoxCPMTTS()
        return LocalTTSAudio(voice=settings.tts_voice, speed=settings.tts_speed)

    async def run(self, scene_plan: dict) -> Path:
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        extension = ".mp3" if self.provider in {"edge", "edge-tts", "elevenlabs"} and not self.mock else ".wav"
        # VoxCPM outputs WAV (48kHz), so it uses the same extension as local
        if self.provider == "voxcpm":
            extension = ".wav"
        audio_path = self.audio_dir / f"narration{extension}"
        subtitles_path = self.audio_dir / "narration.vtt"

        narration_segments = [
            scene.get("narration_segment", "")
            for scene in scene_plan.get("scenes", [])
            if scene.get("narration_segment")
            and scene.get("narration_segment") not in {"Intro branding", "Outro branding"}
        ]
        all_text = " ".join(narration_segments).strip() or "Stoic Modernized"

        if self.mock:
            return await LocalTTSAudio(voice=settings.tts_voice, speed=settings.tts_speed).generate_audio(
                all_text, self.audio_dir / "narration.wav"
            )

        if self.provider == "elevenlabs" and not settings.tts_api_key:
            self.audio_interface = LocalTTSAudio(
                voice=settings.tts_voice, speed=settings.tts_speed
            )
            return await self.audio_interface.generate_audio(all_text, self.audio_dir / "narration.wav")

        try:
            kwargs = {}
            if self.provider in {"edge", "edge-tts"}:
                kwargs["subtitles_path"] = subtitles_path
            return await self.audio_interface.generate_audio(all_text, audio_path, **kwargs)
        except Exception:
            fallback = LocalTTSAudio(voice=settings.tts_voice, speed=settings.tts_speed)
            return await fallback.generate_audio(all_text, self.audio_dir / "narration.wav")

    def save_audio_path(self, audio_path: Path) -> None:
        from src.database import db

        db.update_job(self.job_id, status="tts_complete", audio_path=str(audio_path))

    def load_audio_path(self) -> Optional[str]:
        from src.database import db

        job = db.get_job(self.job_id)
        return job.audio_path if job else None
