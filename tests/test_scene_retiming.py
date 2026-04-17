from src.models import SubtitleSegment
from src.stages.subtitles import SubtitleStage


def test_scene_retiming_uses_scene_starts_not_mid_paragraph(tmp_path):
    stage = SubtitleStage(job_id="retime-test", mock=True)
    stage.job_dir = tmp_path / "jobs" / "retime-test"
    stage.scenes_dir = stage.job_dir / "scenes"
    stage.scenes_dir.mkdir(parents=True, exist_ok=True)

    scene_plan = {
        "scenes": [
            {
                "scene_number": 1,
                "start_time": 0.0,
                "end_time": 4.0,
                "narration_segment": "You can't control the meeting outcome, but you can control your preparation and your response.",
                "visual_prompt": "scene 1",
                "text_overlay": "Control Your Part",
            },
            {
                "scene_number": 2,
                "start_time": 4.0,
                "end_time": 8.0,
                "narration_segment": "That shift is where your power lives.",
                "visual_prompt": "scene 2",
                "text_overlay": "Your Power",
            },
        ],
        "total_duration": 8.0,
    }
    stage._load_scene_plan = lambda: scene_plan

    segments = [
        {"start_time": 0.0, "end_time": 1.2, "text": "You can't control the"},
        {"start_time": 1.2, "end_time": 2.8, "text": "meeting outcome, but you can"},
        {"start_time": 2.8, "end_time": 4.2, "text": "control your preparation and your response."},
        {"start_time": 4.2, "end_time": 5.2, "text": "That shift is where"},
        {"start_time": 5.2, "end_time": 6.4, "text": "your power lives."},
    ]

    subtitle_segments = [SubtitleSegment(**seg) for seg in segments]

    stage._retime_scene_plan_from_vtt_matches(subtitle_segments, audio_duration=6.4)

    updated = stage._load_scene_plan()
    first_scene = updated["scenes"][0]
    second_scene = updated["scenes"][1]

    assert first_scene["start_time"] == 0.0
    assert second_scene["start_time"] == 4.2
    assert first_scene["end_time"] == 4.2
