#!/usr/bin/env python3
"""Simple pipeline runner for Stoic Modernized with a fresh topic."""

import asyncio
import subprocess
import shutil
from pathlib import Path
from src.config import Channel, VideoMode, settings
from src.database import db
from src.utils import load_json, save_json

# Fresh topic: Calendar interruption scenario
topic = "When the Calendar Interrupted Your Deep Work: A Stoic's Guide to Intentional Context Switching"
hook = "Calendar notification: Your focus is dead. Here's how Stoicism saves your attention."

# Create job
job_id = db.create_job(topic).job_id
job_dir = settings.jobs_dir / job_id
job_dir.mkdir(parents=True, exist_ok=True)

print(f"Running Stoic Modernized pipeline")
print(f"Job ID: {job_id}")
print(f"Topic: {topic}")

# Create subdirectories
for subdir in ["research", "script", "scenes", "tts", "images", "subtitles", "render", "output"]:
    (job_dir / subdir).mkdir(exist_ok=True)

# Write script with Stoic angle
script = {
    "title": topic,
    "hook": hook,
    "narration": """Calendar notifications are designed to fragment your attention. Marcus Aurelius wrote about controlling your judgments, not letting external events dictate your peace.

When a meeting invite pops up during deep work, pause before reacting. Ask yourself: is this truly urgent, or just noisy? The Stoic practice of delay transforms irritation into clarity.

Create boundaries around your focus time. Not every interruption deserves your response. True productivity isn't about reacting faster—it's about choosing what matters.

Your attention is your most valuable resource. Guard it like a Stoic guards their virtue.""" ,
    "cta": "What's your best focus protection strategy? Share below.",
    "chapters": [
        {"title": "The Attention Trap", "start_time": 0},
        {"title": "Stoic Pause Practice", "start_time": 10},
        {"title": "Setting Boundaries", "start_time": 20},
        {"title": "Choose What Matters", "start_time": 30},
    ]
}
save_json(script, job_dir / "script" / f"{job_id}-script.json")
print("✓ Script written")

# Generate audio with edge-tts
tts_output = job_dir / "tts" / f"{job_id}-narration.mp3"
edge_binary = shutil.which("edge-tts")
if not edge_binary:
    print("ERROR: edge-tts not found. Install with: pip install edge-tts")
    exit(1)

cmd = [
    edge_binary,
    "--voice", "en-US-GuyNeural",
    "--rate", "+0%",
    "--text", script["narration"],
    "--write-media", str(tts_output),
]
subprocess.run(cmd, check=True, capture_output=True, timeout=120)
print(f"✓ Audio generated: {tts_output}")

# Run pipeline stages
from src.stages.scenes import SceneStage
from src.stages.subtitles import SubtitleStage
from src.stages.render import VideoRenderer
from src.models import Scene, VideoRenderConfig

# Generate scenes
scenes_stage = SceneStage(job_id=job_id, mock=True)
scenes = asyncio.run(scenes_stage.run(script_data=script))
save_json(scenes.model_dump(), job_dir / "scenes" / f"{job_id}-scenes.json")
print("✓ Scenes generated")

# Generate images (real, not mock)
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
    "title": script["title"],
    "description": f"{script['title']}\n\n{script['narration']}",
    "tags": ["stoicism", "productivity", "focus", "deep work"],
    "chapters": script["chapters"],
    "privacy_status": "unlisted",
}
upload_result = asyncio.run(uploader.upload(video_path=render_result.video_path, metadata=metadata))

print("\n" + "=" * 60)
print("✅ PIPELINE COMPLETE!")
print("=" * 60)
print(f"Video URL: {upload_result.video_url}")
print(f"Title: {topic}")
print("=" * 60)
