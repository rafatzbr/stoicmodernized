from pathlib import Path

from src.stages.remotion_renderer import RemotionRenderer


def test_remotion_props_use_phrase_cues_without_word_timing_highlight() -> None:
    renderer = RemotionRenderer(job_id="phrase-caption-test", frontend_dir=Path("/tmp/frontend"))

    props = renderer._generate_props(
        scenes=[
            {
                "scene_number": 1,
                "start_time": 0.0,
                "end_time": 2.0,
                "narration_segment": "When the priority changes.",
                "text_overlay": "Priority",
            }
        ],
        subtitles=[
            {
                "start_time": 0.0,
                "end_time": 1.5,
                "text": "When the priority changes",
                "words": [
                    {"text": "When", "start": 0.0, "end": 0.2},
                    {"text": "the", "start": 0.2, "end": 0.3},
                    {"text": "priority", "start": 0.3, "end": 0.9},
                    {"text": "changes", "start": 0.9, "end": 1.5},
                ],
            }
        ],
        audio_path="audio/narration.wav",
        background_music_path=None,
    )

    assert props["subtitles"] == [
        {
            "startTime": 0.0,
            "endTime": 1.5,
            "text": "When the priority changes",
            "words": None,
        }
    ]
