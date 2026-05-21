"""Remotion renderer for production-quality video output."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

CHANNEL_LOGO_PATH = Path('/home/rafatz/media/logo_transparent.png')

from src.config import Channel, settings
from src.models import Scene, SubtitleSegment
from src.utils import load_json, save_json


def _clean_video_title(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    cleaned = str(title).strip()
    for suffix in (' | Stoic Modernized', ' - Stoic Modernized', ' | The AI Signal', ' - The AI Signal'):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
    return cleaned or None


def _default_platform(mode: str, channel: Channel) -> str:
    if mode != 'portrait':
        return 'youtube'

    if channel == Channel.STOIC_MODERNIZED:
        return 'youtube'

    return 'tiktok'


class RemotionRenderer:
    """Renders videos using Remotion with high-quality effects."""

    def __init__(
        self,
        job_id: str,
        frontend_dir: Path,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        mode: str = 'landscape',  # 'landscape' or 'portrait'
        platform: Optional[str] = None,
        channel: Channel = settings.default_channel,
    ):
        self.job_id = job_id
        self.frontend_dir = frontend_dir
        self.width = width
        self.height = height
        self.fps = fps
        self.mode = mode
        self.platform = platform or _default_platform(mode, channel)
        self.channel = channel
        self.job_dir = Path('/home/rafatz/projects/stoic-modernized/output/jobs') / job_id
        self.public_dir = self.job_dir / 'public'
        self.output_path = self.job_dir / 'remotion_output.mp4'

    def run(self) -> dict:
        """Run the Remotion render pipeline."""
        print(f"[RemotionRenderer] Starting render for job {self.job_id} ({self.mode}, platform={self.platform})")

        # Prepare directories
        self.public_dir.mkdir(parents=True, exist_ok=True)
        self._copy_assets_to_public()

        # Load data
        scenes_data = self._load_scenes()
        subtitles_data = self._load_subtitles()
        audio_path = self._get_audio_path()
        background_music_path = self._get_background_music_path()

        if not scenes_data or not audio_path:
            raise RuntimeError("Missing scenes data or audio file")

        # Generate props
        props = self._generate_props(scenes_data, subtitles_data, audio_path, background_music_path)
        props_path = self.frontend_dir / 'public' / 'props.json'
        save_json(props, props_path)

        print(f"[RemotionRenderer] Props written to {props_path}")

        # Determine composition ID
        composition_id = 'StoicPortrait' if self.mode == 'portrait' else 'StoicLandscape'

        # Run Remotion render
        self._run_remotion_render(composition_id)

        return {
            'video_path': str(self.output_path),
            'width': self.width,
            'height': self.height,
            'duration': props['durationInSeconds'],
            'mode': self.mode,
        }

    def _copy_assets_to_public(self):
        """Copy all required assets to the public directory."""
        images_dir = self.job_dir / 'images'
        audio_dir = self.job_dir / 'audio'
        subtitles_dir = self.job_dir / 'subtitles'
        frontend_public = self.frontend_dir / 'public'

        # Copy assets to frontend's public directory (Remotion v4 serves from here)
        if images_dir.exists():
            for img_file in images_dir.glob('*.jpg'):
                dest = frontend_public / 'images' / img_file.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(img_file, dest)

        if audio_dir.exists():
            # Copy all audio files (wav, mp3, etc.)
            for ext in ['*.wav', '*.mp3', '*.ogg', '*.m4a']:
                for audio_file in audio_dir.glob(ext):
                    dest = frontend_public / 'audio' / audio_file.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(audio_file, dest)
            for vtt_file in audio_dir.glob('*.vtt'):
                dest = frontend_public / 'audio' / vtt_file.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(vtt_file, dest)

        if subtitles_dir.exists():
            for json_file in subtitles_dir.glob('*.json'):
                dest = frontend_public / 'subtitles' / json_file.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(json_file, dest)

        # Always copy branding for Stoic Modernized
        if CHANNEL_LOGO_PATH.exists():
            dest = frontend_public / 'branding' / CHANNEL_LOGO_PATH.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(CHANNEL_LOGO_PATH, dest)

    def _load_scenes(self) -> Optional[list[dict]]:
        """Load scene plan data."""
        scenes_path = self.job_dir / 'scenes' / 'scenes.json'
        if not scenes_path.exists():
            print(f"[RemotionRenderer] Warning: scenes.json not found at {scenes_path}")
            return None

        data = load_json(scenes_path)
        scenes = data.get('scenes', []) if isinstance(data, dict) else []
        return scenes

    def _load_subtitles(self) -> Optional[list[dict]]:
        """Load subtitle data."""
        subs_path = self.job_dir / 'subtitles' / 'subtitles.json'
        if not subs_path.exists():
            print(f"[RemotionRenderer] Warning: subtitles.json not found at {subs_path}")
            return None

        data = load_json(subs_path)
        segments = data.get('segments', []) if isinstance(data, dict) else []
        return segments

    def _get_audio_path(self) -> Optional[str]:
        """Get the narration audio path."""
        audio_dir = self.job_dir / 'audio'
        if not audio_dir.exists():
            return None

        for filename in ('narration.wav', 'narration.mp3', 'narration.ogg', 'narration.m4a'):
            audio_file = audio_dir / filename
            if audio_file.exists():
                return f'audio/{audio_file.name}'

        return None

    def _get_background_music_path(self) -> Optional[str]:
        """Get the relative background music path if present."""
        audio_dir = self.job_dir / 'audio'
        if not audio_dir.exists():
            return None

        for pattern in ('background_music.mp3', 'background_music.wav', 'background_music.ogg', 'background_music.m4a'):
            audio_file = audio_dir / pattern
            if audio_file.exists():
                return f'audio/{audio_file.name}'

        return None

    def _generate_props(
        self,
        scenes: list[dict],
        subtitles: list[dict],
        audio_path: str,
        background_music_path: Optional[str],
    ) -> dict:
        """Generate Remotion render props from pipeline data."""
        scene_total_duration = max((float(scene.get('end_time', 0) or 0) for scene in scenes), default=0.0)
        subtitle_total_duration = max((float(sub.get('end_time', 0) or 0) for sub in subtitles), default=0.0)
        timing_scale = 1.0
        if scene_total_duration > 0 and subtitle_total_duration > scene_total_duration + 0.25:
            timing_scale = subtitle_total_duration / scene_total_duration

        # Build scenes array - use relative paths for staticFile()
        remotion_scenes = []
        for scene in scenes:
            scene_num = int(scene.get('scene_number', 0))
            start_time = float(scene.get('start_time', 0) or 0) * timing_scale
            end_time = float(scene.get('end_time', 0) or 0) * timing_scale
            remotion_scenes.append({
                'sceneNumber': scene_num,
                'imageSrc': f'images/scene_{scene_num:03d}.jpg',
                'startTime': round(start_time, 3),
                'endTime': round(end_time, 3),
                'narrationSegment': scene.get('narration_segment', ''),
                'textOverlay': scene.get('text_overlay'),
                'animationStyle': scene.get('animation_style'),
                'sceneType': scene.get('scene_type'),
                'titleText': scene.get('title_text'),
            })

        # Build subtitles array
        remotion_subtitles = []
        for sub in subtitles:
            words = sub.get('words')
            if words and isinstance(words, list):
                remotion_words = [
                    {
                        'startTime': float(w.get('start', 0)),
                        'endTime': float(w.get('end', 0)),
                        'text': w.get('text', ''),
                    }
                    for w in words
                ]
            else:
                remotion_words = None

            remotion_subtitles.append({
                'startTime': float(sub.get('start_time', 0)),
                'endTime': float(sub.get('end_time', 0)),
                'text': sub.get('text', ''),
                'words': remotion_words,
            })

        # Calculate total duration
        total_duration = max(
            max((scene.get('endTime', 0) for scene in remotion_scenes), default=0.0),
            max((sub.get('endTime', 0) for sub in remotion_subtitles), default=0.0),
        )

        # Get channel metadata from job data if available
        job_data_path = self.job_dir / 'job.json'
        channel_name = settings.get_channel_name(self.channel)
        channel_description = settings.get_channel_description(self.channel)
        channel = self.channel
        if job_data_path.exists():
            job_data = load_json(job_data_path)
            try:
                channel = Channel(job_data.get('channel', channel.value))
            except Exception:
                channel = self.channel
            channel_name = job_data.get('channel_name', settings.get_channel_name(channel))
            channel_description = job_data.get(
                'channel_description',
                settings.get_channel_description(channel),
            )

        # Determine actual video title from job artifacts
        video_title = None
        metadata_path = self.job_dir / 'metadata' / 'metadata.json'
        script_path = self.job_dir / 'script' / 'script.json'
        if metadata_path.exists():
            metadata = load_json(metadata_path)
            video_title = _clean_video_title(metadata.get('title'))
        if not video_title and script_path.exists():
            script_data = load_json(script_path)
            video_title = _clean_video_title(script_data.get('title'))
        if not video_title and scenes:
            video_title = _clean_video_title(scenes[0].get('topic') or scenes[0].get('title'))

        # Get CTA text
        cta_text = settings.get_channel_cta(channel)

        # Use relative path for staticFile()
        audio_relative = audio_path if audio_path else 'audio/narration.mp3'
        logo_relative = (
            f'branding/{CHANNEL_LOGO_PATH.name}'
            if CHANNEL_LOGO_PATH.exists()
            else None
        )

        return {
            'title': video_title or 'Stoic Modernized',
            'topic': scenes[0].get('topic', '') if scenes else '',
            'channelName': channel_name,
            'channelDescription': channel_description,
            'mode': self.mode,
            'platform': self.platform,
            'fps': self.fps,
            'durationInSeconds': total_duration,
            'audioSrc': audio_relative,
            'backgroundMusicSrc': background_music_path,
            'backgroundMusicVolume': settings.background_music_volume,
            'logoSrc': logo_relative,
            'scenes': remotion_scenes,
            'subtitles': remotion_subtitles,
            'ctaText': cta_text,
        }

    def _run_remotion_render(self, composition_id: str):
        """Run the Remotion CLI render command."""
        print(f"[RemotionRenderer] Running: npx remotion render {composition_id} {self.output_path}")

        cmd = [
            'npx',
            'remotion',
            'render',
            str(self.frontend_dir / 'src' / 'remotion' / 'index.ts'),
            composition_id,
            str(self.output_path),
            '--public-dir',
            str(self.frontend_dir / 'public'),
            '--props',
            str(self.frontend_dir / 'public' / 'props.json'),
            '--fps',
            str(self.fps),
            '--width',
            str(self.width),
            '--height',
            str(self.height),
            '--overwrite',
        ]

        if self.mode == 'portrait':
            cmd.extend(['--scale', '1'])

        print(f"[RemotionRenderer] Command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            cwd=str(self.frontend_dir),
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minutes max
        )

        if result.returncode != 0:
            error_msg = f"Remotion render failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            print(error_msg)
            raise RuntimeError(error_msg)

        print(f"[RemotionRenderer] Render complete: {self.output_path}")
        print(f"[RemotionRenderer] STDOUT: {result.stdout[:500]}")
        print(f"[RemotionRenderer] STDERR: {result.stderr[:500]}")
