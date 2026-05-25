import asyncio

from src.stages.subtitles import SubtitleStage
from src.subtitle_timing import parse_webvtt_cues


def test_subtitle_stage_writes_provider_neutral_vtt_sidecar_for_audio_only_fallback(tmp_path, monkeypatch) -> None:
    import src.stages.subtitles as subtitles_module

    monkeypatch.setattr(subtitles_module.settings, "subtitle_asr_enabled", False)

    stage = SubtitleStage(job_id="heuristic-vtt-test", mock=True)
    stage.job_dir = tmp_path / "jobs" / "heuristic-vtt-test"
    stage.subtitles_dir = stage.job_dir / "subtitles"
    stage.audio_dir = stage.job_dir / "audio"
    stage.scenes_dir = stage.job_dir / "scenes"
    stage.audio_dir.mkdir(parents=True)
    audio_path = stage.audio_dir / "narration.mp3"
    audio_path.write_bytes(b"fake audio bytes")
    monkeypatch.setattr(stage, "_get_audio_duration", lambda path: 6.0)

    result = asyncio.run(
        stage.run(
            {
                "narration": (
                    "You do not control the interruption. "
                    "You control whether it becomes your day."
                )
            },
            audio_path=str(audio_path),
        )
    )

    vtt_path = stage.subtitles_dir / "subtitles.vtt"
    assert vtt_path.exists()
    vtt_text = vtt_path.read_text(encoding="utf-8")
    assert vtt_text.startswith("WEBVTT\n\n")
    cues = parse_webvtt_cues(vtt_text, source="heuristic")
    assert [cue.text for cue in cues] == [segment.text for segment in result.segments]
    assert cues[0].start_time == result.segments[0].start_time
    assert cues[-1].end_time == 6.0


def test_scene_plan_fallback_scales_all_scene_text_to_actual_audio_duration(tmp_path, monkeypatch) -> None:
    import src.stages.subtitles as subtitles_module

    monkeypatch.setattr(subtitles_module.settings, "subtitle_asr_enabled", False)

    stage = SubtitleStage(job_id="kokoro-shorter-than-estimate", mock=True)
    stage.job_dir = tmp_path / "jobs" / "kokoro-shorter-than-estimate"
    stage.subtitles_dir = stage.job_dir / "subtitles"
    stage.audio_dir = stage.job_dir / "audio"
    stage.scenes_dir = stage.job_dir / "scenes"
    stage.scenes_dir.mkdir(parents=True, exist_ok=True)
    stage.audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = stage.audio_dir / "narration.wav"
    audio_path.write_bytes(b"fake audio bytes")
    monkeypatch.setattr(stage, "_get_audio_duration", lambda path: 33.0)

    scene_plan = {
        "total_duration": 54.0,
        "scenes": [
            {
                "scene_number": 1,
                "start_time": 0.0,
                "end_time": 18.0,
                "narration_segment": "First sentence. Second sentence.",
            },
            {
                "scene_number": 2,
                "start_time": 18.0,
                "end_time": 54.0,
                "narration_segment": "Third sentence. Final visible step should remain in captions.",
            },
        ],
    }
    stage._load_scene_plan = lambda: scene_plan

    result = asyncio.run(
        stage.run(
            {
                "narration": (
                    "First sentence. Second sentence. Third sentence. "
                    "Final visible step should remain in captions."
                )
            },
            audio_path=str(audio_path),
        )
    )

    subtitle_text = " ".join(segment.text for segment in result.segments)
    assert "Final visible step should remain in captions." in subtitle_text
    assert result.segments[-1].end_time == 33.0
    assert all(segment.end_time > segment.start_time for segment in result.segments)
