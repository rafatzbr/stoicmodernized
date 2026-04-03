from pathlib import Path

import pytest

from src.config import VideoMode, settings
from src.stages.images import ImageGenerationStage
from src.stages.render import VideoRenderer
from src.stages.scenes import SceneStage
from src.stages.script import ScriptStage
from src.stages.subtitles import SubtitleStage


@pytest.mark.asyncio
async def test_short_mode_script_is_shorter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = ScriptStage(job_id="short-job", mock=True, video_mode=VideoMode.SHORT)
    result = await stage.run({"topic": "workplace stress", "title": "Workplace Stress"})

    assert "[0:50-0:58]" in result.narration
    assert len(result.chapters) == 4


@pytest.mark.asyncio
async def test_short_mode_scene_plan_stays_within_short_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    script_stage = ScriptStage(job_id="short-job", mock=True, video_mode=VideoMode.SHORT)
    script = await script_stage.run({"topic": "workplace stress", "title": "Workplace Stress"})

    scene_stage = SceneStage(job_id="short-job", mock=True)
    scene_plan = await scene_stage.run(script.model_dump(mode="json"))

    assert scene_plan.total_duration <= 60.0
    assert len(scene_plan.scenes) == 4
    overlays = [scene.text_overlay for scene in scene_plan.scenes]
    assert len(set(overlays)) == len(overlays)
    assert not any(overlay in {"Time", "Overthinking"} for overlay in overlays if overlay)
    assert all("gold accents" not in scene.visual_prompt for scene in scene_plan.scenes)
    assert all("modern editorial photo" in scene.visual_prompt for scene in scene_plan.scenes)


@pytest.mark.asyncio
async def test_subtitles_use_audio_duration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = SubtitleStage(job_id="sub-job", mock=False)
    stage.job_dir = tmp_path / "jobs" / "sub-job"
    stage.subtitles_dir = stage.job_dir / "subtitles"

    stage._get_audio_duration = lambda _path: 12.0
    result = await stage.run(
        {"narration": "[0:00-0:10] Intro\nOne short line.\nAnother slightly longer line."},
        "dummy.mp3",
    )

    assert result.segments[-1].end_time == 12.0
    assert result.segments[0].start_time == 0.0
    assert len(result.segments) >= 2
    assert all(len(segment.text.split()) <= 6 for segment in result.segments)


@pytest.mark.asyncio
async def test_placeholder_only_images_skip_sd_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = ImageGenerationStage(job_id="img-job", mock=False, placeholder_only=True)
    stage.job_dir = tmp_path / "jobs" / "img-job"
    stage.images_dir = stage.job_dir / "images"
    stage._sd_cli_available = lambda: True  # type: ignore[method-assign]

    assets = await stage.run(
        {
            "topic": "How to Stop FOMO from Ruining Your Career Focus",
            "scenes": [
                {
                    "scene_number": 1,
                    "visual_prompt": "roman bust in a modern office",
                    "text_overlay": "Control",
                }
            ],
        }
    )

    assert len(assets) == 1
    assert Path(assets[0].image_path).exists()
    assert "How to Stop FOMO from Ruining Your Career Focus" in assets[0].prompt


def test_edge_tts_segments_use_raw_timing_chunks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = SubtitleStage(job_id="edge-job", mock=False)
    stage.job_dir = tmp_path / "jobs" / "edge-job"
    stage.audio_dir = stage.job_dir / "audio"
    stage.audio_dir.mkdir(parents=True, exist_ok=True)
    raw_line = "This is a much longer subtitle line that should stay exactly as emitted by edge tts."
    (stage.audio_dir / "narration.vtt").write_text(
        f"1\n00:00:00,100 --> 00:00:04,100\n{raw_line}\n",
        encoding="utf-8",
    )

    segments = stage._load_edge_tts_segments()
    assert len(segments) == 1
    assert segments[0].text == raw_line
    assert segments[0].start_time == 0.1
    assert segments[0].end_time == 4.1


@pytest.mark.asyncio
async def test_edge_tts_segments_are_cleaned_and_clamped_to_audio_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    stage = SubtitleStage(job_id="edge-clean-job", mock=False)
    stage.job_dir = tmp_path / "jobs" / "edge-clean-job"
    stage.audio_dir = stage.job_dir / "audio"
    stage.subtitles_dir = stage.job_dir / "subtitles"
    stage.audio_dir.mkdir(parents=True, exist_ok=True)
    (stage.audio_dir / "narration.vtt").write_text(
        "1\n00:00:00,000 --> 00:00:03,200\nNext time you feel anxiety rising, ask: 'What part of this is actually in my hands?\n",
        encoding="utf-8",
    )
    stage._get_audio_duration = lambda _path: 3.0  # type: ignore[method-assign]

    result = await stage.run({"narration": ""}, "dummy.mp3")

    assert result.segments[0].text == "Next time you feel anxiety rising, ask: What part of this is actually in my hands?"
    assert result.segments[0].end_time == 3.0


def test_short_render_endcard_starts_last_three_seconds_and_persists_to_end() -> None:
    renderer = VideoRenderer(job_id="render-job", mock=False)
    filter_text = renderer._build_endcard_drawtext(21.0)
    assert "gte(t,18.00)" in filter_text


def test_render_uses_audio_duration_as_output_cap(tmp_path: Path) -> None:
    renderer = VideoRenderer(job_id="render-job", mock=False)
    renderer.output_dir = tmp_path / "output"
    renderer.output_dir.mkdir(parents=True, exist_ok=True)
    image_path = tmp_path / "scene.jpg"
    image_path.write_bytes(b"fake-image")
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"fake-audio")
    output_path = tmp_path / "final.mp4"

    captured = {}

    def fake_run(cmd, capture_output, text, check):
        captured["cmd"] = cmd

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("src.stages.render.subprocess.run", fake_run)
    try:
        class SceneObj:
            animation_style = "zoom"

        renderer.render_scene_sequence(
            scenes=[SceneObj()],
            images=[image_path],
            audio_path=audio_path,
            output_path=output_path,
            durations=[57.7],
            audio_duration=55.296,
        )
    finally:
        monkeypatch.undo()

    assert "-t" in captured["cmd"]
    assert "55.296" in captured["cmd"]


def test_scene_durations_follow_scene_timing_when_audio_present() -> None:
    renderer = VideoRenderer(job_id="render-job", mock=False)

    class SceneObj:
        def __init__(self, start, end):
            self.start_time = start
            self.end_time = end

    durations = renderer._scene_durations([SceneObj(0, 10), SceneObj(10, 20), SceneObj(20, 23)], 23.0)
    assert len(durations) == 3
    assert durations[0] > durations[2]
    assert round(sum(durations), 2) == 23.0


def test_real_image_prompt_uses_natural_language_scene_description() -> None:
    stage = ImageGenerationStage(job_id="img-job", mock=False, placeholder_only=False)

    prompt = stage._compose_image_prompt(
        subject="How to Stop Overthinking Work Problems with Stoic Control",
        scene_prompt="A single focused worker in a modern minimalist office returning to one task at a clean, organized desk. Vertical 9:16 frame, no text, no logo.",
        overlay="Replay Loop",
    )

    assert prompt.startswith("A single focused worker in a modern minimalist office")
    assert "The image should emphasize replay loop." in prompt
    assert "Keep the scene clearly connected to the video topic: How to Stop Overthinking Work Problems with Stoic Control." in prompt
    assert "Use a single clear subject, modern workplace realism, calm natural lighting, sharp focus, and a vertical 9:16 composition." in prompt
    assert "vertical 9:16 frame" not in prompt.lower()
    assert "no text" not in prompt.lower()
    assert "no logo" not in prompt.lower()


def test_short_scene_overlay_avoids_philosopher_names() -> None:
    stage = SceneStage(job_id="scene-job", mock=True)

    overlay = stage._generate_text_overlay(
        "Marcus Aurelius reminded us that our peace depends on distinguishing between what is up to us and what is not. In the office, your preparation and attitude are yours to command, but the client's mood or the boss's final decision are not.",
        "Stop Overthinking Work Problems with Stoic Control",
    )

    assert overlay == "Control Your Part"


def test_short_scene_visual_prompt_centers_takeaway_not_philosopher() -> None:
    stage = SceneStage(job_id="scene-job", mock=True)

    prompt = stage._generate_visual_prompt(
        "Stop Overthinking Work Problems with Stoic Control",
        "Marcus Aurelius reminded us that our peace depends on distinguishing between what is up to us and what is not. In the office, your preparation and attitude are yours to command, but the client's mood or the boss's final decision are not.",
        scene_num=2,
        is_short=True,
    )

    assert "professional at desk weighing a checklist against incoming feedback" in prompt
    assert "clear contrast between what can be acted on and what must be released" in prompt
    assert "Marcus Aurelius" not in prompt


@pytest.mark.asyncio
async def test_subtitles_retime_scene_boundaries_from_vtt_phrase_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))

    job_dir = tmp_path / "jobs" / "scene-retime"
    scenes_dir = job_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    (scenes_dir / "scenes.json").write_text(
        '{"scenes":['
        '{"scene_number":1,"start_time":0.0,"end_time":12.0,"narration_segment":"Stop replaying the meeting in your head.","visual_prompt":"vp1","text_overlay":"Hook"},'
        '{"scene_number":2,"start_time":12.0,"end_time":30.0,"narration_segment":"Ask what is actually in your control right now.","visual_prompt":"vp2","text_overlay":"Principle"},'
        '{"scene_number":3,"start_time":30.0,"end_time":50.0,"narration_segment":"Put your energy into the next useful action.","visual_prompt":"vp3","text_overlay":"Application"},'
        '{"scene_number":4,"start_time":50.0,"end_time":58.0,"narration_segment":"Use this the next time your mind starts spiraling.","visual_prompt":"vp4","text_overlay":"CTA"}'
        '],"total_duration":58.0}',
        encoding="utf-8",
    )

    stage = SubtitleStage(job_id="scene-retime", mock=False)
    stage.job_dir = job_dir
    stage.subtitles_dir = job_dir / "subtitles"
    stage.scenes_dir = scenes_dir
    stage.audio_dir = job_dir / "audio"
    stage.audio_dir.mkdir(parents=True, exist_ok=True)
    (stage.audio_dir / "narration.vtt").write_text(
        """1
00:00:00,100 --> 00:00:02,000
Stop replaying the meeting in your head.

2
00:00:02,000 --> 00:00:04,500
Ask what is actually in your control right now.

3
00:00:04,500 --> 00:00:07,000
Put your energy into the next useful action.

4
00:00:07,000 --> 00:00:09,000
Use this the next time your mind starts spiraling.
""",
        encoding="utf-8",
    )
    stage._get_audio_duration = lambda _path: 9.0

    script_data = {
        "narration": """[0:00-0:12] Hook
Stop replaying the meeting in your head.

[0:12-0:30] Stoic Principle
Ask what is actually in your control right now.

[0:30-0:50] Workplace Application
Put your energy into the next useful action.

[0:50-0:58] CTA
Use this the next time your mind starts spiraling."""
    }

    await stage.run(script_data, "dummy.mp3")

    import json

    scenes = json.loads((scenes_dir / "scenes.json").read_text())["scenes"]
    assert scenes[0]["start_time"] == 0.1
    assert scenes[1]["start_time"] == 2.0
    assert scenes[2]["start_time"] == 4.5
    assert scenes[3]["start_time"] == 7.0
    assert scenes[3]["end_time"] == 9.0


def test_zoom_animation_style_uses_duration_aware_zoompan_filter() -> None:
    renderer = VideoRenderer(job_id="render-job", mock=False)
    filter_text = renderer._build_scene_clip_filter(width=1080, height=1920, duration=12.0, animation_style="zoom")
    assert "zoompan=" in filter_text
    assert "s=1080x1920" in filter_text
    assert "1.08" in filter_text
    assert "0.000" in filter_text


def test_non_zoom_animation_style_uses_static_filter() -> None:
    renderer = VideoRenderer(job_id="render-job", mock=False)
    filter_text = renderer._build_scene_clip_filter(width=1080, height=1920, duration=6.0, animation_style="fade")
    assert "zoompan=" not in filter_text
    assert "fps=" in filter_text
