"""Video rendering stage module using ffmpeg."""

import subprocess
from pathlib import Path
from typing import Optional

from src.config import settings
from src.models import VideoRenderConfig, VideoRenderResult


class VideoRenderer:
    """Handles video rendering using ffmpeg."""

    def __init__(self, job_id: str, mock: bool = False):
        self.job_id = job_id
        self.mock = mock or settings.mock_mode
        self.job_dir = settings.jobs_dir / job_id
        self.output_dir = self.job_dir / "output"
        self.width = settings.video_width
        self.height = settings.video_height
        self.fps = settings.video_fps
        self.background_music_volume = settings.background_music_volume

    async def run(self, config: VideoRenderConfig) -> VideoRenderResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.mock:
            return await self._mock_render(config)
        return await self._real_render(config)

    async def _mock_render(self, config: VideoRenderConfig) -> VideoRenderResult:
        return await self._real_render(config)

    async def _real_render(self, config: VideoRenderConfig) -> VideoRenderResult:
        output_path = Path(config.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        thumbnail_path = self.output_dir / "thumbnail.jpg"

        audio_duration = await self._get_audio_duration(Path(config.audio_path))
        durations = self._scene_durations(config.scenes, audio_duration)
        image_paths = self._resolve_image_paths(config.scenes)

        self.render_scene_sequence(
            images=image_paths,
            audio_path=Path(config.audio_path),
            output_path=output_path,
            durations=durations,
            subtitle_path=Path(config.subtitle_path) if config.subtitle_path else None,
            width=config.width,
            height=config.height,
        )

        if image_paths:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(image_paths[0]),
                    "-frames:v",
                    "1",
                    str(thumbnail_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        duration = audio_duration or sum(durations)
        return VideoRenderResult(
            video_path=str(output_path),
            duration=duration,
            thumbnail_path=str(thumbnail_path),
        )

    async def _get_audio_duration(self, audio_path: Path) -> Optional[float]:
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(probe.stdout.strip())
        except Exception:
            return None

    def _scene_durations(self, scenes: list, audio_duration: Optional[float]) -> list[float]:
        if not scenes:
            return [3.0]
        if audio_duration and audio_duration > 0:
            duration = audio_duration / len(scenes)
            return [max(0.8, duration) for _ in scenes]

        durations = []
        for scene in scenes:
            raw = float(scene.end_time - scene.start_time)
            durations.append(max(1.0, raw))
        return durations or [3.0]

    def _resolve_image_paths(self, scenes: list) -> list[Path]:
        image_dir = self.job_dir / "images"
        paths = []
        for scene in scenes:
            scene_number = scene.scene_number if hasattr(scene, "scene_number") else scene["scene_number"]
            path = image_dir / f"scene_{scene_number:03d}.jpg"
            if path.exists():
                paths.append(path)
        return paths

    def render_scene_sequence(
        self,
        images: list[Path],
        audio_path: Path,
        output_path: Path,
        durations: list[float],
        subtitle_path: Optional[Path] = None,
        width: int = 1920,
        height: int = 1080,
    ) -> subprocess.CompletedProcess:
        if not images:
            raise RuntimeError("No scene images found for rendering")

        concat_file = self.output_dir / "images.txt"
        lines = []
        for image, duration in zip(images, durations, strict=False):
            lines.append(f"file '{image.as_posix()}'")
            lines.append(f"duration {duration:.3f}")
        lines.append(f"file '{images[-1].as_posix()}'")
        concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        video_filter = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={self.fps},format=yuv420p"
        if subtitle_path:
            video_filter += f",subtitles={subtitle_path.as_posix()}"

        logo_path = settings.watermark_logo_path
        if logo_path.exists():
            filter_complex = (
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},fps={self.fps},format=yuv420p[base];"
                f"[2:v]scale={settings.watermark_scale_width}:-1[wm];"
                f"[base][wm]overlay=W-w-{settings.watermark_padding}:H-h-{settings.watermark_padding}[tmp]"
            )
            if subtitle_path:
                filter_complex += f";[tmp]subtitles={subtitle_path.as_posix()}[vout]"
            else:
                filter_complex += ";[tmp]null[vout]"

            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-i",
                str(audio_path),
                "-i",
                str(logo_path),
                "-filter_complex",
                filter_complex,
                "-map",
                "[vout]",
                "-map",
                "1:a:0",
                "-r",
                str(self.fps),
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
            ]
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-i",
                str(audio_path),
                "-vf",
                video_filter,
                "-r",
                str(self.fps),
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
            ]

        return subprocess.run(cmd, capture_output=True, text=True, check=True)
