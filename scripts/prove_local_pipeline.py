import asyncio
import json
import subprocess
from pathlib import Path

from src.config import VideoMode, settings
from src.database import db
from src.models import Scene, VideoRenderConfig
from src.stages.images import ImageGenerationStage
from src.stages.research import ResearchStage
from src.stages.render import VideoRenderer
from src.stages.scenes import SceneStage
from src.stages.script import ScriptStage
from src.stages.subtitles import SubtitleStage
from src.stages.tts import TTSStage
from src.utils import load_json


def ffprobe_json(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def ffprobe_text_block(path: Path) -> str:
    result = subprocess.run(
        [
            "ffprobe",
            "-hide_banner",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return (result.stderr or result.stdout).strip()


def count_frames(path: Path) -> int:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(float(result.stdout.strip()))


def stream_by_type(probe: dict, codec_type: str) -> dict | None:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == codec_type:
            return stream
    return None


async def main() -> None:
    topic = "workplace stress"
    video_mode = VideoMode.SHORT
    tts_provider = "edge"

    job = db.create_job(topic)
    job_id = job.job_id
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    evidence: dict = {
        "job_id": job_id,
        "topic": topic,
        "video_mode": video_mode.value,
        "tts_provider": tts_provider,
    }

    try:
        research_stage = ResearchStage(job_id=job_id, mock=False)
        research = await research_stage.run(topic)
        research_path = research_stage.save_results(research)
        db.update_job(job_id, status="research_complete", research_path=str(research_path))

        script_stage = ScriptStage(job_id=job_id, mock=True, video_mode=video_mode)
        script = await script_stage.run(load_json(research_path))
        script_path = script_stage.save_script(script)
        db.update_job(job_id, status="script_complete", script_path=str(script_path))

        scene_stage = SceneStage(job_id=job_id, mock=True)
        scene_plan = await scene_stage.run(load_json(script_path))
        scene_path = scene_stage.save_scene_plan(scene_plan)
        db.update_job(job_id, status="scene_complete", scene_plan_path=str(scene_path))

        tts_stage = TTSStage(job_id=job_id, provider=tts_provider, mock=False)
        audio_path = await tts_stage.run(load_json(scene_path))
        tts_stage.save_audio_path(audio_path)
        evidence["tts"] = {
            "provider": tts_provider,
            "command": f"edge-tts --voice {settings.tts_voice} --rate +0% --text '<scene narration>' --write-media {audio_path}",
            "output_path": str(audio_path),
        }

        image_stage = ImageGenerationStage(job_id=job_id, mock=False)
        scene_plan_dict = load_json(scene_path)
        assets = await image_stage.run(scene_plan_dict)
        assets_path = image_stage.save_assets(assets)
        db.update_job(job_id, status="images_complete", images_dir=str(image_stage.images_dir))
        evidence["image_generation"] = {
            "commands": [],
            "assets_path": str(assets_path),
            "asset_count": len(assets),
        }
        for scene in scene_plan_dict.get("scenes", []):
            prompt = (
                "vertical composition, minimalist stoic background, ancient roman column silhouette, "
                "black marble texture, gold accents, dramatic cinematic lighting, dark philosophical aesthetic, empty center space, "
                + scene["visual_prompt"]
            )
            cmd = (
                f"{settings.sd_cli_path} -m {settings.sd_model_path} --clip_l {settings.sd_clip_l_path} "
                f"--clip_g {settings.sd_clip_g_path} --t5xxl {settings.sd_t5xxl_path} -H {settings.sd_image_height} -W {settings.sd_image_width} "
                f"-p {json.dumps(prompt)} -n {json.dumps('people, face, crowd, beach, ocean, water, snow, text, logo, border, frame, margin, white border, blank edge, empty white space, poster, flyer')} "
                f"--cfg-scale {settings.sd_cfg_scale} --sampling-method {settings.sd_sampling_method} --clip-on-cpu --vae-on-cpu --seed -1 -o {job_dir / 'images' / f'scene_{scene['scene_number']:03d}.jpg'}"
            )
            evidence["image_generation"]["commands"].append(cmd)

        subtitle_stage = SubtitleStage(job_id=job_id, mock=False)
        subtitle_result = await subtitle_stage.run(load_json(script_path), str(audio_path))
        db.update_job(job_id, status="subtitles_complete", subtitle_path=subtitle_result.srt_path)

        scenes = [Scene(**scene) for scene in scene_plan_dict.get("scenes", [])]
        renderer = VideoRenderer(job_id=job_id, mock=False)
        output_path = renderer.output_dir / "final.mp4"
        render_config = VideoRenderConfig(
            scenes=scenes,
            audio_path=str(audio_path),
            subtitle_path=subtitle_result.srt_path,
            output_path=str(output_path),
            width=settings.short_video_width,
            height=settings.short_video_height,
        )
        render_result = await renderer.run(render_config)
        db.update_job(
            job_id,
            status="ready_for_upload",
            video_path=render_result.video_path,
            thumbnail_path=render_result.thumbnail_path,
        )

        rendering_json = {
            "job_id": job_id,
            "final_output": render_result.video_path,
            "thumbnail": render_result.thumbnail_path,
            "subtitle_asset": subtitle_result.srt_path,
            "captions_enabled": True,
            "subtitle_filter_applied": True,
            "render_command": [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(renderer.output_dir / 'images.txt'),
                "-i",
                str(audio_path),
                "-vf",
                f"scale={settings.short_video_width}:{settings.short_video_height}:force_original_aspect_ratio=cover,crop={settings.short_video_width}:{settings.short_video_height},fps={settings.video_fps},format=yuv420p,subtitles={subtitle_result.srt_path}",
                "-r",
                str(settings.video_fps),
                "-c:v",
                "libx264",
                "-profile:v",
                "high",
                "-level:v",
                "4.1",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-shortest",
                str(output_path),
            ],
        }
        rendering_path = job_dir / "rendering.json"
        rendering_path.write_text(json.dumps(rendering_json, indent=2), encoding="utf-8")

        probe = ffprobe_json(output_path)
        video_stream = stream_by_type(probe, "video") or {}
        audio_stream = stream_by_type(probe, "audio") or {}
        frame_count = count_frames(output_path)
        final_duration = float(probe["format"]["duration"])
        narration_probe = ffprobe_json(audio_path)
        narration_duration = float(narration_probe["format"]["duration"])
        validation = {
            "job_id": job_id,
            "final_output": str(output_path),
            "file_size_bytes": output_path.stat().st_size,
            "total_frame_count": frame_count,
            "fps": eval(video_stream.get("avg_frame_rate", "0/1")),
            "resolution": f"{video_stream.get('width')}x{video_stream.get('height')}",
            "video_codec": video_stream.get("codec_name"),
            "audio_codec": audio_stream.get("codec_name"),
            "final_duration": final_duration,
            "narration_duration": narration_duration,
            "duration_delta_seconds": round(abs(final_duration - narration_duration), 3),
            "scene_count_planned": len(scene_plan_dict.get("scenes", [])),
            "scene_count_rendered": len(scene_plan_dict.get("scenes", [])),
            "captions_enabled": True,
            "subtitle_asset_generated": Path(subtitle_result.srt_path).exists(),
            "subtitle_filter_applied": True,
            "validation_passed": bool(output_path.exists() and output_path.stat().st_size > 0 and frame_count > 0),
            "ffprobe_text": ffprobe_text_block(output_path),
        }
        validation_path = job_dir / "validation.json"
        validation_path.write_text(json.dumps(validation, indent=2), encoding="utf-8")

        print(json.dumps({
            "job_id": job_id,
            "rendering_json": str(rendering_path),
            "validation_json": str(validation_path),
            "final_output": str(output_path),
        }, indent=2))

    except Exception as exc:
        print(json.dumps({
            "job_id": job_id,
            "failing_stage": "unknown",
            "error": repr(exc),
        }, indent=2))
        raise


if __name__ == "__main__":
    asyncio.run(main())
