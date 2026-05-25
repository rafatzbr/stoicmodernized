import asyncio

from src.stages.subtitles import SubtitleStage
from src.subtitle_timing import TimedWord, parse_webvtt_cues


def test_subtitle_stage_can_use_optional_forced_alignment_before_asr(tmp_path, monkeypatch) -> None:
    import src.stages.subtitles as subtitles_module

    monkeypatch.setattr(subtitles_module.settings, "subtitle_asr_enabled", True)
    monkeypatch.setattr(subtitles_module.settings, "tts_subtitles_timing", "align")
    monkeypatch.setattr(subtitles_module.settings, "tts_subtitles_alignment_enabled", True, raising=False)

    stage = SubtitleStage(job_id="forced-align-test", mock=True)
    stage.job_dir = tmp_path / "jobs" / "forced-align-test"
    stage.subtitles_dir = stage.job_dir / "subtitles"
    stage.audio_dir = stage.job_dir / "audio"
    stage.scenes_dir = stage.job_dir / "scenes"
    stage.audio_dir.mkdir(parents=True)
    audio_path = stage.audio_dir / "narration.mp3"
    audio_path.write_bytes(b"fake audio bytes")
    monkeypatch.setattr(stage, "_get_audio_duration", lambda path: 4.0)

    def fake_align(audio_path_arg: str, transcript: str):
        assert audio_path_arg == str(audio_path)
        assert transcript == "You control the next action. Let the noise pass."
        return [
            TimedWord(text="You", start_time=0.10, end_time=0.30, source="alignment"),
            TimedWord(text="control", start_time=0.30, end_time=0.70, source="alignment"),
            TimedWord(text="the", start_time=0.70, end_time=0.85, source="alignment"),
            TimedWord(text="next", start_time=0.85, end_time=1.15, source="alignment"),
            TimedWord(text="action.", start_time=1.15, end_time=1.70, source="alignment"),
            TimedWord(text="Let", start_time=2.00, end_time=2.20, source="alignment"),
            TimedWord(text="the", start_time=2.20, end_time=2.35, source="alignment"),
            TimedWord(text="noise", start_time=2.35, end_time=2.70, source="alignment"),
            TimedWord(text="pass.", start_time=2.70, end_time=3.20, source="alignment"),
        ]

    monkeypatch.setattr(stage, "_align_transcript_words", fake_align)
    monkeypatch.setattr(stage, "_transcribe_audio_segments", lambda path: (_ for _ in ()).throw(AssertionError("ASR should not run when alignment succeeds")))

    result = asyncio.run(
        stage.run(
            {"narration": "You control the next action. Let the noise pass."},
            audio_path=str(audio_path),
        )
    )

    assert [segment.text for segment in result.segments] == [
        "You control the next action.",
        "Let the noise pass.",
    ]
    assert result.segments[0].words is not None
    assert result.segments[0].words[0]["source"] == "alignment"

    vtt_path = stage.subtitles_dir / "subtitles.vtt"
    cues = parse_webvtt_cues(vtt_path.read_text(encoding="utf-8"), source="alignment")
    assert [cue.text for cue in cues] == [segment.text for segment in result.segments]
    assert cues[0].start_time == 0.1
    assert cues[-1].end_time == 3.2


def test_forced_alignment_is_skipped_when_disabled(monkeypatch) -> None:
    import src.stages.subtitles as subtitles_module

    monkeypatch.setattr(subtitles_module.settings, "tts_subtitles_timing", "auto")
    monkeypatch.setattr(subtitles_module.settings, "tts_subtitles_alignment_enabled", False, raising=False)

    stage = SubtitleStage(job_id="forced-align-disabled", mock=True)

    assert stage._should_attempt_alignment("Anything", audio_path="narration.mp3") is False
