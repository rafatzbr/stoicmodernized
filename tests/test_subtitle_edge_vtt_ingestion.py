from src.models import SubtitleSegment
from src.stages.subtitles import SubtitleStage
from src.subtitle_timing import TimedCue


def test_subtitle_stage_loads_edge_vtt_through_normalized_timing_layer(tmp_path, monkeypatch) -> None:
    import src.stages.subtitles as subtitles_module

    calls = []

    def fake_parse_webvtt_cues(text: str, *, source: str = "unknown"):
        calls.append((text, source))
        return [
            TimedCue(
                start_time=1.2,
                end_time=3.8,
                text="You do not control the interruption.",
                source=source,
            ),
            TimedCue(
                start_time=3.9,
                end_time=6.6,
                text="You control whether it becomes your day.",
                source=source,
            ),
        ]

    monkeypatch.setattr(subtitles_module, "parse_webvtt_cues", fake_parse_webvtt_cues)

    stage = SubtitleStage(job_id="edge-vtt-test", mock=True)
    stage.audio_dir = tmp_path / "audio"
    stage.audio_dir.mkdir(parents=True)
    (stage.audio_dir / "narration.vtt").write_text(
        "WEBVTT\n\n"
        "00:00:01.200 --> 00:00:03.800\n"
        "You do not control the interruption.\n\n"
        "00:00:03.900 --> 00:00:06.600\n"
        "You control whether it becomes your day.\n",
        encoding="utf-8",
    )

    segments = stage._load_edge_tts_segments()

    assert calls and calls[0][1] == "edge"
    assert segments == [
        SubtitleSegment(
            start_time=1.2,
            end_time=3.8,
            text="You do not control the interruption.",
        ),
        SubtitleSegment(
            start_time=3.9,
            end_time=6.6,
            text="You control whether it becomes your day.",
        ),
    ]
