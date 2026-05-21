from pathlib import Path

import pytest

from src.models import Scene, VideoRenderConfig
from src.stages.images import ImageGenerationStage
from src.stages.render import VideoRenderer
from src.stages.subtitles import SubtitleStage
from src.stages.tts import EdgeTTSAudio, TTSStage


@pytest.mark.asyncio
async def test_local_pipeline_stages_create_real_assets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    from src.config import Settings

    test_settings = Settings()

    job_id = "asset-job"
    scene_plan = {
        "scenes": [
            {
                "scene_number": 0,
                "start_time": 0.0,
                "end_time": 2.0,
                "narration_segment": "Intro branding",
                "visual_prompt": "dark marble with gold accents",
                "text_overlay": "Stoic Modernized",
            },
            {
                "scene_number": 1,
                "start_time": 2.0,
                "end_time": 5.0,
                "narration_segment": "Control your reaction, not the meeting.",
                "visual_prompt": "roman bust in a modern office",
                "text_overlay": "Control",
            },
        ]
    }

    async def fake_edge_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        _ = self, text, kwargs
        import math
        import struct
        import wave

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 16_000
        duration_seconds = 1.0
        with wave.open(str(output_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            for i in range(int(sample_rate * duration_seconds)):
                sample = int(1600 * math.sin(2 * math.pi * 440 * i / sample_rate))
                handle.writeframes(struct.pack("<h", sample))
        return output_path

    monkeypatch.setattr(EdgeTTSAudio, "generate_audio", fake_edge_audio)

    tts_stage = TTSStage(job_id=job_id, provider="edge", mock=False)
    tts_stage.job_dir = test_settings.jobs_dir / job_id
    tts_stage.audio_dir = tts_stage.job_dir / "audio"
    audio_path = await tts_stage.run(scene_plan)
    assert audio_path.exists()
    assert audio_path.stat().st_size > 1000

    image_stage = ImageGenerationStage(job_id=job_id, mock=False, placeholder_only=True, allow_placeholder_override=True)
    image_stage.job_dir = test_settings.jobs_dir / job_id
    image_stage.images_dir = image_stage.job_dir / "images"
    assets = await image_stage.run(scene_plan)
    assert assets
    for asset in assets:
        path = Path(asset.image_path)
        assert path.exists()
        assert path.stat().st_size > 0

    subtitle_stage = SubtitleStage(job_id=job_id, mock=False)
    subtitle_stage.job_dir = test_settings.jobs_dir / job_id
    subtitle_stage.subtitles_dir = subtitle_stage.job_dir / "subtitles"
    subtitles = await subtitle_stage.run(
        {
            "narration": "[0:00-0:02] Intro\nControl your reaction, not the meeting."
        },
        str(audio_path),
    )
    assert Path(subtitles.srt_path).exists()
    assert "Control your reaction" in Path(subtitles.srt_path).read_text(encoding="utf-8")

    renderer = VideoRenderer(job_id=job_id, mock=False)
    renderer.job_dir = test_settings.jobs_dir / job_id
    renderer.output_dir = renderer.job_dir / "output"
    config = VideoRenderConfig(
        scenes=[
            Scene(**scene_plan["scenes"][0]),
            Scene(**scene_plan["scenes"][1]),
        ],
        audio_path=str(audio_path),
        subtitle_path=subtitles.srt_path,
        output_path=str(renderer.output_dir / "final.mp4"),
    )
    result = await renderer.run(config)
    assert Path(result.video_path).exists()
    assert Path(result.video_path).stat().st_size > 0
    assert Path(result.thumbnail_path).exists()
