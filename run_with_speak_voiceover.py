#!/usr/bin/env python3
"""Run AI Signal pipeline with pre-existing Speak TTS voiceover."""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, UTC
import typer

from src.config import Channel, VideoMode, settings
from src.database import db
from src.utils import save_json, load_json
from src.stages.research import ResearchStage
from src.stages.script import ScriptStage
from src.stages.scenes import SceneStage
from src.stages.tts import TTSAudioInterface
from src.stages.music import BackgroundMusicStage
from src.stages.images import ImageGenerationStage
from src.stages.subtitles import SubtitleStage
from src.stages.render import VideoRenderer
from src.stages.upload import YouTubeUploader
from src.stages.quality_gate import QualityGateStage, QualityGateError

app = typer.Typer()


class SpeakTTSAudio(TTSAudioInterface):
    """Use pre-existing Speak TTS audio files."""
    
    name = "speak"
    
    def __init__(self, voiceover_job_id: str, channel: Channel):
        self.voiceover_job_id = voiceover_job_id
        self.channel = channel
        self.job_dir = settings.jobs_dir / voiceover_job_id
        self.audio_dir = self.job_dir / "tts"
        
    async def generate_audio(self, text: str, output_path: Path, **kwargs) -> Path:
        """Copy the pre-generated Speak audio to the expected output location."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Find the Speak-generated audio file
        audio_files = list(self.audio_dir.glob("*.mp3"))
        if not audio_files:
            # Try to find in the job directory itself
            audio_files = list(self.job_dir.glob("*.mp3"))
            
        if not audio_files:
            raise RuntimeError(f"No audio files found in {self.audio_dir} or {self.job_dir}")
        
        # Copy the first audio file (should be the main narration)
        import shutil
        shutil.copy(audio_files[0], output_path)
        
        return output_path


@app.command()
def run_with_voiceover(
    topic: str = typer.Argument(..., help="Topic for the video"),
    voiceover_job_id: str = typer.Argument(..., help="Speak TTS job ID"),
    video_mode: VideoMode = typer.Option(VideoMode.SHORT, "--video-mode", "-m", help="Video mode: short or long"),
    hook: str = typer.Option(None, "--hook", "-h", help="YouTube hook/title override"),
) -> None:
    """Run the complete pipeline using a pre-existing Speak TTS voiceover."""
    
    # Create job record
    job_record = db.create_job(topic)
    job_id = job_record.job_id
    
    channel = settings.default_channel
    print(f"Running pipeline with Speak voiceover: {voiceover_job_id}")
    print(f"New job ID: {job_id}")
    print(f"Channel: {channel.value}")
    
    # Load the voiceover script from Speak job
    speak_job_path = settings.jobs_dir / voiceover_job_id / f"{voiceover_job_id}.json"
    if not speak_job_path.exists():
        # Try as file directly
        speak_job_path = settings.jobs_dir / f"{voiceover_job_id}.json"
    
    if not speak_job_path.exists():
        raise RuntimeError(f"Speak TTS job not found: {speak_job_path}")
    
    speak_job = load_json(speak_job_path)
    voiceover_script = speak_job.get("voiceover_script")
    
    if not voiceover_script:
        raise RuntimeError(f"No voiceover_script found in Speak job {voiceover_job_id}")
    
    print(f"Voiceover script loaded ({len(voiceover_script)} chars)")
    
    # Create output directory structure
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    (job_dir / "research").mkdir(exist_ok=True)
    (job_dir / "script").mkdir(exist_ok=True)
    (job_dir / "scenes").mkdir(exist_ok=True)
    (job_dir / "tts").mkdir(exist_ok=True)
    (job_dir / "images").mkdir(exist_ok=True)
    (job_dir / "subtitles").mkdir(exist_ok=True)
    (job_dir / "render").mkdir(exist_ok=True)
    
    # Step 1: Research (mock since we have the script)
    print("\n[1/8] Running research stage (mock)...")
    research_stage = ResearchStage(job_id=job_id, mock=True, channel=channel)
    research_result = asyncio.run(research_stage.run(topic=topic))
    # Convert Pydantic model to dict for JSON serialization
    save_json(research_result.model_dump(), job_dir / "research" / f"{job_id}-research.json")
    
    # Step 2: Script (use voiceover script directly)
    print("\n[2/8] Running script stage...")
    script_dir = job_dir / "script"
    
    # Determine title and hook
    title = topic if not hook else hook
    if not hook:
        # Use a default hook based on the voiceover
        hook = "Top 5 AI News Today"
    
    script = {
        "title": title,
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
    
    save_json(script, script_dir / f"{job_id}-script.json")
    
    # Step 3: Scenes
    print("\n[3/8] Running scenes stage...")
    scenes_stage = SceneStage(job_id=job_id, mock=True, channel=channel)
    # Load script data and pass to scenes
    script_data = load_json(script_dir / f"{job_id}-script.json")
    scenes = asyncio.run(scenes_stage.run(script_data=script_data))
    save_json(scenes.model_dump(), job_dir / "scenes" / f"{job_id}-scenes.json")
    
    # Step 4: TTS (use edge-tts to generate audio from Speak-optimized script)
    print("\n[4/8] Running TTS stage (generating from Speak script)...")
    tts_output = job_dir / "tts" / f"{job_id}-narration.mp3"
    tts_output.parent.mkdir(parents=True, exist_ok=True)
    
    import subprocess
    import shutil
    
    # Use edge-tts to generate audio from the Speak-optimized script
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
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        print(f"Audio generated: {tts_output}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("edge-tts timed out")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"edge-tts failed: {e.stderr}")
    
    # Step 5: Music
    print("\n[5/8] Running music stage...")
    try:
        tts_output = job_dir / "tts" / f"{job_id}-narration.mp3"
        music_stage = BackgroundMusicStage(job_id=job_id)
        music_result = asyncio.run(music_stage.run(topic=topic, audio_path=str(tts_output)))
        save_json({"audio_path": str(music_result)}, job_dir / "music" / f"{job_id}-music.json")
    except Exception as e:
        print(f"Music stage skipped: {e}")
    
    # Step 6: Images
    print("\n[6/8] Running images stage...")
    images_stage = ImageGenerationStage(job_id=job_id, mock=True)
    scenes_data = load_json(job_dir / "scenes" / f"{job_id}-scenes.json")
    images_result = asyncio.run(images_stage.run(scene_plan=scenes_data))
    save_json([img.model_dump() if hasattr(img, 'model_dump') else img for img in images_result], job_dir / "images" / f"{job_id}-images.json")
    
    # Step 7: Subtitles
    print("\n[7/8] Running subtitles stage...")
    tts_output = job_dir / "tts" / f"{job_id}-narration.mp3"
    subtitles_stage = SubtitleStage(job_id=job_id)
    subtitles_result = asyncio.run(subtitles_stage.run(script_data=script_data, audio_path=str(tts_output)))
    save_json(subtitles_result.model_dump(), job_dir / "subtitles" / f"{job_id}-subtitles.json")
    
    # Step 8: Render
    print("\n[8/8] Running render stage...")
    from src.stages.render import VideoRenderer
    tts_output = job_dir / "tts" / f"{job_id}-narration.mp3"
    renderer = VideoRenderer(job_id=job_id, mock=True)
    render_result = asyncio.run(renderer.run())
    print(f"Render result: {render_result}")
    
    # Upload
    print("\nUploading to YouTube...")
    from src.stages.upload import YouTubeUploader
    uploader = YouTubeUploader(mock=False, channel=channel)
    upload_result = asyncio.run(uploader.upload(job_id=job_id))
    print(f"Upload result: {upload_result}")
    
    print("\n✅ Pipeline complete!")
    print(f"Job ID: {job_id}")
    print(f"Output: {job_dir}")


if __name__ == "__main__":
    app()
