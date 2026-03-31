from pathlib import Path

import pytest

from src.stages.tts import TTSStage


@pytest.mark.asyncio
async def test_edge_tts_provider_generates_audio_or_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TTS_VOICE", "en-US-GuyNeural")

    from src.config import Settings

    test_settings = Settings()

    stage = TTSStage(job_id="edge-job", provider="edge", mock=False)
    stage.job_dir = test_settings.jobs_dir / "edge-job"
    stage.audio_dir = stage.job_dir / "audio"

    path = await stage.run(
        {
            "scenes": [
                {
                    "scene_number": 1,
                    "narration_segment": "Stoicism helps you control your response to stress.",
                }
            ]
        }
    )

    assert path.exists()
    assert path.suffix in {".mp3", ".wav"}
    assert path.stat().st_size > 0
