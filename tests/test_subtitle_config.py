import asyncio

from src.config import Settings
from src.stages.subtitles import SubtitleStage


def test_subtitle_video_workflow_config_defaults_to_vtt_auto_readable_heuristic() -> None:
    settings = Settings()

    assert settings.tts_subtitles_enabled is True
    assert settings.tts_subtitles_format == "vtt"
    assert settings.tts_subtitles_timing == "auto"
    assert settings.tts_subtitles_phrase_style == "readable"
    assert settings.tts_subtitles_fallback == "heuristic"
    assert settings.tts_subtitles_alignment_enabled is False
    assert settings.tts_subtitles_aligner == "stable-ts"
    assert settings.tts_subtitles_aligner_model == "base.en"


def test_subtitle_stage_respects_disabled_vtt_sidecar_config(tmp_path, monkeypatch) -> None:
    import src.stages.subtitles as subtitles_module

    monkeypatch.setattr(subtitles_module.settings, "subtitle_asr_enabled", False)
    monkeypatch.setattr(subtitles_module.settings, "tts_subtitles_enabled", False)

    stage = SubtitleStage(job_id="subtitle-config-test", mock=True)
    stage.job_dir = tmp_path / "jobs" / "subtitle-config-test"
    stage.subtitles_dir = stage.job_dir / "subtitles"
    stage.audio_dir = stage.job_dir / "audio"
    stage.scenes_dir = stage.job_dir / "scenes"
    stage.audio_dir.mkdir(parents=True)
    stage.subtitles_dir.mkdir(parents=True)
    stale_vtt = stage.subtitles_dir / "subtitles.vtt"
    stale_vtt.write_text("WEBVTT\n\nstale\n", encoding="utf-8")
    audio_path = stage.audio_dir / "narration.mp3"
    audio_path.write_bytes(b"fake audio bytes")
    monkeypatch.setattr(stage, "_get_audio_duration", lambda path: 4.0)

    result = asyncio.run(
        stage.run(
            {"narration": "Choose the next right action. Let the noise pass."},
            audio_path=str(audio_path),
        )
    )

    assert result.srt_path.endswith("subtitles.srt")
    assert (stage.subtitles_dir / "subtitles.srt").exists()
    assert (stage.subtitles_dir / "subtitles.json").exists()
    assert not stale_vtt.exists()
