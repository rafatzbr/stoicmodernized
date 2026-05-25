from pathlib import Path
import sys
import types

import pytest

from src.config import Settings, TTSProvider
from src.stages.tts import KokoroTTSAudio, TTSStage


def test_kokoro_provider_config_is_available() -> None:
    settings = Settings()

    assert TTSProvider.KOKORO.value == "kokoro"
    assert settings.kokoro_command == "kokoro-tts"
    assert settings.kokoro_voice == "bm_lewis"
    assert settings.kokoro_format == "wav"
    assert settings.kokoro_timeout_seconds > 0
    assert settings.kokoro_language == "en-gb"


@pytest.mark.asyncio
async def test_kokoro_stage_generates_audio_without_native_vtt_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def fake_generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        assert isinstance(self, KokoroTTSAudio)
        assert "Choose the next right action" in text
        assert "subtitles_path" not in kwargs
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake kokoro mp3")
        return output_path

    monkeypatch.setattr(KokoroTTSAudio, "generate_audio", fake_generate_audio)

    stage = TTSStage(job_id="kokoro-job", provider="kokoro", mock=False)
    stage.job_dir = tmp_path / "jobs" / "kokoro-job"
    stage.audio_dir = stage.job_dir / "audio"

    path = await stage.run(
        {
            "scenes": [
                {"scene_number": 1, "narration_segment": "Intro branding"},
                {
                    "scene_number": 2,
                    "narration_segment": "Choose the next right action while the room gets loud.",
                },
                {"scene_number": 3, "narration_segment": "Outro branding"},
            ]
        }
    )

    assert path == stage.audio_dir / "narration.wav"
    assert path.exists()
    assert path.stat().st_size > 0
    assert not (stage.audio_dir / "narration.vtt").exists()


def test_kokoro_audio_invokes_configured_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import src.stages.tts as tts_module

    calls = []

    def fake_which(binary: str) -> str:
        assert binary == "kokoro-tts"
        return "/usr/local/bin/kokoro-tts"

    def fake_run(cmd, check, capture_output, timeout):
        calls.append((cmd, check, capture_output, timeout))
        output_path = Path(cmd[cmd.index("--output") + 1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake kokoro mp3")
        return None

    monkeypatch.setattr(tts_module.shutil, "which", fake_which)
    monkeypatch.setattr(tts_module.subprocess, "run", fake_run)

    audio = KokoroTTSAudio(command="kokoro-tts", voice="af_sarah", speed=1.05, timeout_seconds=42)
    output = tmp_path / "narration.mp3"

    import asyncio

    path = asyncio.run(audio.generate_audio("One calm sentence.", output))

    assert path == output
    assert output.read_bytes() == b"fake kokoro mp3"
    cmd, check, capture_output, timeout = calls[0]
    assert cmd == [
        "/usr/local/bin/kokoro-tts",
        "--text",
        "One calm sentence.",
        "--output",
        str(output),
        "--voice",
        "af_sarah",
        "--speed",
        "1.05",
    ]
    assert check is True
    assert capture_output is True
    assert timeout == 42


def test_kokoro_audio_uses_direct_onnx_when_model_files_exist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []

    model_path = tmp_path / "kokoro-v1.0.onnx"
    voices_path = tmp_path / "voices-v1.0.bin"
    model_path.write_bytes(b"fake model")
    voices_path.write_bytes(b"fake voices")

    class FakeKokoro:
        def __init__(self, model: str, voices: str):
            calls.append(("init", model, voices))

        def create(self, text: str, voice: str, speed: float, lang: str):
            calls.append(("create", text, voice, speed, lang))
            return [0.0, 0.1, -0.1], 24000

    def fake_write(path: Path, samples, sample_rate: int) -> None:
        calls.append(("write", path, list(samples), sample_rate))
        path.write_bytes(b"fake wav")

    monkeypatch.setitem(sys.modules, "kokoro_onnx", types.SimpleNamespace(Kokoro=FakeKokoro))
    monkeypatch.setitem(sys.modules, "soundfile", types.SimpleNamespace(write=fake_write))

    audio = KokoroTTSAudio(
        command="kokoro-tts",
        voice="bm_lewis",
        speed=0.95,
        model_path=model_path,
        voices_path=voices_path,
        language="en-gb",
    )

    import asyncio

    output = tmp_path / "narration.wav"
    path = asyncio.run(audio.generate_audio("One direct sentence.", output))

    assert path == output
    assert output.read_bytes() == b"fake wav"
    assert calls == [
        ("init", str(model_path), str(voices_path)),
        ("create", "One direct sentence.", "bm_lewis", 0.95, "en-gb"),
        ("write", output, [0.0, 0.1, -0.1], 24000),
    ]


def test_kokoro_audio_falls_back_to_cli_when_direct_onnx_renderer_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import asyncio
    import src.stages.tts as tts_module

    model_path = tmp_path / "kokoro-v1.0.onnx"
    voices_path = tmp_path / "voices-v1.0.bin"
    model_path.write_bytes(b"fake model")
    voices_path.write_bytes(b"fake voices")
    calls = []

    def fake_generate_with_kokoro_onnx(self, text: str, output_path: Path) -> Path:
        calls.append(("direct", text, output_path))
        raise RuntimeError("direct renderer dependency missing")

    def fake_which(binary: str) -> str:
        assert binary == "kokoro-tts"
        return "/usr/local/bin/kokoro-tts"

    def fake_run(cmd, check, capture_output, timeout):
        calls.append(("cli", cmd, check, capture_output, timeout))
        output_path = Path(cmd[cmd.index("--output") + 1])
        output_path.write_bytes(b"fallback wav")
        return None

    monkeypatch.setattr(KokoroTTSAudio, "_generate_with_kokoro_onnx", fake_generate_with_kokoro_onnx)
    monkeypatch.setattr(tts_module.shutil, "which", fake_which)
    monkeypatch.setattr(tts_module.subprocess, "run", fake_run)

    audio = KokoroTTSAudio(
        command="kokoro-tts",
        voice="bm_lewis",
        model_path=model_path,
        voices_path=voices_path,
    )
    output = tmp_path / "narration.wav"

    path = asyncio.run(audio.generate_audio("Fallback sentence.", output))

    assert path == output
    assert output.read_bytes() == b"fallback wav"
    assert calls[0] == ("direct", "Fallback sentence.", output)
    assert calls[1][0] == "cli"
