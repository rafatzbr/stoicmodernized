#!/usr/bin/env python3
"""Simple AI Signal pipeline runner."""

import asyncio
from pathlib import Path
from src.config import Channel, VideoMode, settings
from src.database import db
from src.utils import load_json, save_json

# Load Speak voiceover script
speak_job = load_json(settings.jobs_dir / "speak-tts-2026-05-10T08-10-00.json")
voiceover_script = speak_job.get("voiceover_script")
hook = "Nvidia just launched a chip that could end Intel's 30-year AI monopoly"

# Create job
job_record = db.create_job("Top 5 AI News Today")
job_id = job_record.job_id
job_dir = settings.jobs_dir / job_id
job_dir.mkdir(parents=True, exist_ok=True)

print(f"Running AI Signal pipeline with Speak TTS")
print(f"Job ID: {job_id}")

# Create subdirectories
for subdir in ["research", "script", "scenes", "tts", "images", "subtitles", "render", "output"]:
    (job_dir / subdir).mkdir(exist_ok=True)

# Write script
script = {
    "title": "Top 5 AI News Today",
    "hook": hook,
    "narration": voiceover_script,
    "cta": "What do you think? Let me know in the comments.",
    "chapters": [
        {"title": "Hardware Competition", "start_time": 0},
        {"title": "Regulatory Oversight", "start_time": 15},
        {"title": "Open Source Safety", "start_time": 30},
        {"title": "Scientific AI", "start_time": 45},
    ]
}
save_json(script, job_dir / "script" / f"{job_id}-script.json")
print("✓ Script written")

# Generate audio with edge-tts
import subprocess
import shutil
tts_output = job_dir / "tts" / f"{job_id}-narration.mp3"
edge_binary = shutil.which("edge-tts")
cmd = [
    edge_binary,
    "--voice", "en-US-GuyNeural",
    "--rate", "+0%",
    "--text", voiceover_script,
    "--write-media", str(tts_output),
]
subprocess.run(cmd, check=True, capture_output=True, timeout=120)
print(f"✓ Audio generated: {tts_output}")

# Now run the actual pipeline stages
from src.stages.scenes import SceneStage
from src.stages.subtitles import SubtitleStage
from src.stages.render import VideoRenderer
from src.stages.upload import YouTubeUploader
from src.models import Scene, VideoRenderConfig

# Generate scenes
scenes_stage = SceneStage(job_id=job_id, mock=True)
scenes = asyncio.run(scenes_stage.run(script_data=script))
save_json(scenes.model_dump(), job_dir / "scenes" / f"{job_id}-scenes.json")
print("✓ Scenes generated")

# Generate images
from src.stages.images import ImageGenerationStage
images_stage = ImageGenerationStage(job_id=job_id, mock=False)
images_result = asyncio.run(images_stage.run(scene_plan=scenes.model_dump()))
print(f"✓ Generated {len(images_result)} images")

# Generate subtitles
subtitles_stage = SubtitleStage(job_id=job_id)
subtitles_result = asyncio.run(subtitles_stage.run(script_data=script, audio_path=str(tts_output)))
save_json(subtitles_result.model_dump(), job_dir / "subtitles" / f"{job_id}-subtitles.json")
print("✓ Subtitles generated")

# Render video
scenes_list = [Scene(**s) for s in scenes.model_dump()["scenes"]]
render_config = VideoRenderConfig(
    scenes=scenes_list,
    audio_path=str(tts_output),
    subtitle_path=str(job_dir / "subtitles" / f"{job_id}-subtitles.srt"),
    output_path=str(job_dir / "output" / f"{job_id}-video.mp4"),
    width=settings.short_video_width,
    height=settings.short_video_height,
)

renderer = VideoRenderer(job_id=job_id, mock=False)
render_result = asyncio.run(renderer.run(config=render_config))
print(f"✓ Video rendered: {render_result.video_path}")

# Upload to YouTube
uploader = YouTubeUploader(mock=False, channel=Channel.STOIC_MODERNIZED)
metadata = {
    "title": hook,
    "description": f"{script['title']}\n\n{voiceover_script}",
    "tags": ["AI", "technology", "news"],
    "chapters": script["chapters"],
    "privacy_status": "unlisted",
}
upload_result = asyncio.run(uploader.upload(video_path=render_result.video_path, metadata=metadata))

print("\n" + "=" * 60)
print("✅ PIPELINE COMPLETE!")
print("=" * 60)
print(f"Video URL: {upload_result.video_url}")
print(f"Title: {hook}")
print("=" * 60)
