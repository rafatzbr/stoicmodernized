#!/usr/bin/env python3
"""Run AI Signal video pipeline directly."""

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, UTC

from src.config import Channel, VideoMode, settings
from src.database import db
from src.utils import load_json, save_json
from src.models import Scene, VideoRenderConfig
from src.stages.research import ResearchStage
from src.stages.script import ScriptStage
from src.stages.scenes import SceneStage
from src.stages.subtitles import SubtitleStage
from src.stages.music import BackgroundMusicStage
from src.stages.images import ImageGenerationStage
from src.stages.render import VideoRenderer
from src.stages.upload import YouTubeUploader


async def main():
    """Run the complete AI Signal pipeline."""
    
    # Configuration
    topic = "Top 5 AI News Today"
    voiceover_job_id = "speak-tts-2026-05-10T08-10-00"
    hook = "Nvidia just launched a chip that could end Intel's 30-year AI monopoly"
    video_mode = VideoMode.SHORT
    channel = Channel.STOIC_MODERNIZED
    
    # Create job
    job_record = db.create_job(topic)
    job_id = job_record.job_id
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Running AI Signal pipeline with Speak TTS script")
    print(f"Job ID: {job_id}")
    
    # Load voiceover script from Speak job
    speak_job_path = settings.jobs_dir / f"{voiceover_job_id}.json"
    speak_job = load_json(speak_job_path)
    voiceover_script = speak_job.get("voiceover_script")
    
    if not voiceover_script:
        raise RuntimeError(f"No voiceover_script found in {voiceover_job_id}")
    
    print(f"✓ Loaded voiceover script ({len(voiceover_script)} chars)")
    
    # Create directory structure
    for subdir in ["research", "script", "scenes", "tts", "images", "subtitles", "output"]:
        (job_dir / subdir).mkdir(exist_ok=True)
    
    # Step 1: Research (mock)
    print("\n[1/7] Running research stage (mock)...")
    research_stage = ResearchStage(job_id=job_id, mock=True, channel=channel)
    research_result = await research_stage.run(topic=topic)
    save_json(research_result.model_dump(), job_dir / "research" / f"{job_id}-research.json")
    print("✓ Research complete")
    
    # Step 2: Script (use voiceover script directly)
    print("\n[2/7] Writing script...")
    script = {
        "title": topic,
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
    
    # Step 3: Scenes
    print("\n[3/7] Generating scenes...")
    scenes_stage = SceneStage(job_id=job_id, mock=True, channel=channel)
    scenes = await scenes_stage.run(script_data=script)
    save_json(scenes.model_dump(), job_dir / "scenes" / f"{job_id}-scenes.json")
    print("✓ Scenes generated")
    
    # Step 4: TTS (edge-tts with Speak-optimized script)
    print("\n[4/7] Generating audio with edge-tts...")
    tts_output = job_dir / "tts" / f"{job_id}-narration.mp3"
    tts_output.parent.mkdir(parents=True, exist_ok=True)
    
    edge_binary = shutil.which("edge-tts")
    if not edge_binary:
        raise RuntimeError("edge-tts is not installed")
    
    cmd = [
        edge_binary,
        "--voice", "en-US-GuyNeural",
        "--rate", "+0%",
        "--text", voiceover_script,
        "--write-media", str(tts_output),
    ]
    
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    print(f"✓ Audio generated: {tts_output}")
    
    # Step 5: Music
    print("\n[5/7] Adding background music...")
    music_stage = BackgroundMusicStage(job_id=job_id)
    music_path = await music_stage.run(topic=topic, audio_path=str(tts_output))
    save_json({"audio_path": str(music_path)}, job_dir / "music" / f"{job_id}-music.json")
    print(f"✓ Music added: {music_path}")
    
    # Step 6: Images
    print("\n[6/7] Generating images...")
    images_stage = ImageGenerationStage(job_id=job_id, mock=True)
    images_result = await images_stage.run(scene_plan=scenes.model_dump())
    save_json([img.model_dump() if hasattr(img, 'model_dump') else img for img in images_result], 
              job_dir / "images" / f"{job_id}-images.json")
    print(f"✓ Generated {len(images_result)} images")
    
    # Step 7: Render & Upload
    print("\n[7/7] Rendering and uploading...")
    
    # Load scenes
    scenes_data = load_json(job_dir / "scenes" / f"{job_id}-scenes.json")
    scenes_list = [Scene(**scene) for scene in scenes_data.get('scenes', scenes_data)]
    
    # Load subtitles
    subtitles_path = job_dir / "subtitles" / f"{job_id}-subtitles.srt"
    if not subtitles_path.exists():
        # Create empty subtitle file
        subtitles_path.write_text("")
    
    # Create render config
    render_config = VideoRenderConfig(
        scenes=scenes_list,
        audio_path=str(tts_output),
        subtitle_path=str(subtitles_path),
        output_path=str(job_dir / "output" / f"{job_id}-video.mp4"),
        width=settings.short_video_width if video_mode == VideoMode.SHORT else settings.video_width,
        height=settings.short_video_height if video_mode == VideoMode.SHORT else settings.video_height,
    )
    
    renderer = VideoRenderer(job_id=job_id, mock=True)
    render_result = await renderer.run(config=render_config)
    print(f"✓ Render complete: {render_result.video_path}")
    
    # Upload
    uploader = YouTubeUploader(mock=False, channel=channel)
    
    # Create metadata
    metadata = {
        "title": hook,
        "description": f"{topic} - AI Signal\n\n{voiceover_script}",
        "tags": ["AI", "technology", "news", "AI Signal"],
        "chapters": script["chapters"],
        "privacy_status": "unlisted",
    }
    
    upload_result = await uploader.upload(video_path=render_result.video_path, metadata=metadata)
    
    print("\n" + "=" * 60)
    print("✅ PIPELINE COMPLETE!")
    print("=" * 60)
    print(f"Job ID: {job_id}")
    print(f"Video URL: {upload_result.video_url}")
    print(f"Title: {metadata['title']}")
    print(f"Status: {upload_result.upload_status}")
    print("=" * 60)
    
    return upload_result


if __name__ == "__main__":
    result = asyncio.run(main())
