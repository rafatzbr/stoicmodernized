"""Video rendering stage module using ffmpeg."""

import subprocess
from pathlib import Path
from typing import Optional

import ffmpeg

from src.config import settings
from src.models import VideoRenderConfig, VideoRenderResult


class VideoRenderer:
    """Handles video rendering using ffmpeg."""

    def __init__(self, job_id: str, mock: bool = False):
        """Initialize video renderer.

        Args:
            job_id: Unique job identifier
            mock: If True, use mock data
        """
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.job_dir = settings.jobs_dir / job_id
        self.output_dir = self.job_dir / "output"

        # Video settings
        self.width = settings.video_width
        self.height = settings.video_height
        self.fps = settings.video_fps
        self.background_music_volume = settings.background_music_volume

    async def run(self, config: VideoRenderConfig) -> VideoRenderResult:
        """Render final video from scenes.

        Args:
            config: VideoRenderConfig with all assets and settings

        Returns:
            VideoRenderResult with output paths
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if self.mock:
            return await self._mock_render(config)
        else:
            return await self._real_render(config)

    async def _mock_render(self, config: VideoRenderConfig) -> VideoRenderResult:
        """Mock video rendering."""
        output_path = Path(config.output_path)
        output_path.touch()  # Create empty file

        # Create mock thumbnail
        thumbnail_path = self.output_dir / "thumbnail.jpg"
        thumbnail_path.touch()

        return VideoRenderResult(
            video_path=str(output_path),
            duration=300.0,  # Mock 5-minute video
            thumbnail_path=str(thumbnail_path),
        )

    async def _real_render(self, config: VideoRenderConfig) -> VideoRenderResult:
        """Real video rendering using ffmpeg.

        TODO: Implement full ffmpeg pipeline with:
        - Scene transitions
        - Background images/videos
        - Audio mixing (voiceover + background music)
        - Subtitle burning
        - Text overlays
        - Intro/outro branding
        """
        output_path = Path(config.output_path)
        thumbnail_path = self.output_dir / "thumbnail.jpg"

        # Get audio duration
        audio_duration = await self._get_audio_duration(config.audio_path)

        # Build ffmpeg filter complex for scenes
        # This is a simplified version - full implementation would handle
        # dynamic scene transitions and overlays

        # Example ffmpeg command structure:
        # ffmpeg -i background.mp4 -i audio.wav -i subtitles.srt -filter_complex ... -c:v libx264 -c:a aac output.mp4

        # For now, create a simple placeholder
        output_path.touch()
        thumbnail_path.touch()

        return VideoRenderResult(
            video_path=str(output_path),
            duration=audio_duration or 300.0,
            thumbnail_path=str(thumbnail_path),
        )

    async def _get_audio_duration(self, audio_path: Path) -> Optional[float]:
        """Get audio duration using ffprobe.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds, or None if error
        """
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ],
                capture_output=True,
                text=True,
            )

            if probe.returncode == 0:
                return float(probe.stdout.strip())

        except Exception:
            pass

        return None

    def render_with_ffmpeg(
        self,
        scenes: list[dict],
        audio_path: Path,
        output_path: Path,
        background_music_path: Optional[Path] = None,
        subtitle_path: Optional[Path] = None,
        intro_image: Optional[Path] = None,
        outro_image: Optional[Path] = None,
    ) -> subprocess.CompletedProcess:
        """Build and execute ffmpeg command.

        This is the core rendering logic. In production, this would:
        1. Create filters for each scene transition
        2. Add text overlays at appropriate times
        3. Burn in subtitles
        4. Mix audio with background music
        5. Add intro/outro branding

        Args:
            scenes: List of scene data with timing and visuals
            audio_path: Path to narration audio
            output_path: Output video path
            background_music_path: Optional background music
            subtitle_path: Optional subtitle file
            intro_image: Optional intro image
            outro_image: Optional outro image

        Returns:
            CompletedProcess result
        """
        # This is a simplified placeholder
        # Full implementation would build complex filter chains

        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-i", str(audio_path),  # Audio
        ]

        # Add background music if provided
        if background_music_path:
            cmd.extend(["-i", str(background_music_path)])

        # Add subtitles if provided
        if subtitle_path:
            cmd.extend(["-vf", f"subtitles={subtitle_path}"])

        # Add output encoding
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-vf", f"scale={self.width}:{self.height},fps={self.fps}",
            str(output_path),
        ])

        return subprocess.run(cmd, capture_output=True, text=True)

    def render_scene_sequence(
        self,
        images: list[Path],
        audio_path: Path,
        output_path: Path,
        durations: list[float],
    ) -> subprocess.CompletedProcess:
        """Render a sequence of images with audio.

        Args:
            images: List of image paths for each scene
            audio_path: Narration audio
            output_path: Output video path
            durations: Duration for each image in seconds

        Returns:
            CompletedProcess result
        """
        # Build input arguments for all images
        inputs = []
        filter_complex = []

        # Add each image as input
        for i, image in enumerate(images):
            inputs.extend(["-loop", "1", "-i", str(image)])
            filter_complex.append(f"[{i}:v]trim=start={sum(durations[:i])}:duration={durations[i]},setpts=PTS-STARTPTS[v{i}]")

        # Concatenate video streams
        concat_inputs = " ".join(f"[v{i}]" for i in range(len(images)))
        filter_complex.append(f"{concat_inputs}concat=n={len(images)}:v=1:a=0[vout]")

        # Add audio
        inputs.extend(["-i", str(audio_path)])
        filter_complex.append("[1:a]atrim=0:duration={}[aout]".format(sum(durations)))

        filter_complex.append(f"[vout][aout]")

        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", ",".join(filter_complex)]
        cmd.extend(["-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-c:a", "aac", str(output_path)])

        return subprocess.run(cmd, capture_output=True, text=True)
