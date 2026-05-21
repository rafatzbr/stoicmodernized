"""Video rendering stage module using ffmpeg."""

import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image

from src.config import Channel, settings
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
            scenes=config.scenes,
            images=image_paths,
            audio_path=Path(config.audio_path),
            output_path=output_path,
            durations=durations,
            subtitle_path=Path(config.subtitle_path) if config.subtitle_path else None,
            width=config.width,
            height=config.height,
            add_short_endcard=(config.width == settings.short_video_width and config.height == settings.short_video_height),
            audio_duration=audio_duration,
            background_music_path=Path(config.background_music_path) if config.background_music_path else None,
        )

        if image_paths:
            # Load title from research JSON for thumbnail
            research_json = self.job_dir / "research" / "research.json"
            title = "Stoic Modernized"
            if research_json.exists():
                try:
                    import json as _json
                    with open(research_json) as _f:
                        _data = _json.load(_f)
                        title = _data.get("title", title)
                except Exception:
                    pass
            # Generate a proper thumbnail with title overlay and branding
            thumbnail = self._generate_thumbnail(
                source_image=image_paths[0],
                title=title,
                output_path=thumbnail_path,
                width=config.width,
                height=config.height,
            )

        duration = audio_duration or sum(durations)
        return VideoRenderResult(
            video_path=str(output_path),
            duration=duration,
            thumbnail_path=str(thumbnail_path),
        )

    def _generate_thumbnail(
        self,
        *,
        source_image: Path,
        title: str,
        output_path: Path,
        width: int,
        height: int,
    ) -> Path:
        """Generate a proper thumbnail with title overlay, branding, and contrast.

        Creates a YouTube-ready thumbnail (1280x720) with:
        - The source image as background with a dark overlay for readability
        - Bold title text with shadow
        - Channel branding at the bottom
        """
        from PIL import Image, ImageDraw, ImageFont

        output_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_width = 1280
        thumb_height = 720

        # Load source image and use it as background
        with Image.open(source_image) as src:
            src = src.convert("RGB")
            # Resize to fit thumbnail dimensions while preserving aspect ratio
            src.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            thumb_bg = Image.new("RGB", (thumb_width, thumb_height), (0, 0, 0))
            # Center the source image
            thumb_bg.paste(src, ((thumb_width - src.width) // 2, (thumb_height - src.height) // 2))

        # Apply a dark gradient overlay for text readability
        overlay = Image.new("RGBA", (thumb_width, thumb_height), (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        for y in range(thumb_height):
            alpha = min(int(140 * (y / thumb_height)), 160)
            draw_overlay.line([(0, y), (thumb_width, y)], fill=(0, 0, 0, alpha))

        thumb_bg = thumb_bg.convert("RGBA")
        thumb_bg = Image.alpha_composite(thumb_bg, overlay)

        # Draw text
        draw = ImageDraw.Draw(thumb_bg)

        # Try to load a bold font, fall back to default
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        font_size = 48
        font = None
        for fp in font_paths:
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        # Wrap title to fit
        lines = []
        words = title.split()
        line = ""
        max_width = thumb_width - 80
        for word in words:
            test = f"{line} {word}".strip() if line else word
            bbox = draw.textbbox((0, 0), test, font=font)
            text_w = bbox[2] - bbox[0]
            if text_w <= max_width:
                line = test
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)

        # Draw each title line with shadow for readability
        for i, text_line in enumerate(lines):
            bbox = draw.textbbox((0, 0), text_line, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = (thumb_width - text_w) // 2
            y = 60 + i * (font_size + 12)
            # Shadow
            draw.text((x + 2, y + 2), text_line, font=font, fill=(0, 0, 0, 200))
            # Main text in white with gold accent
            draw.text((x, y), text_line, font=font, fill=(255, 255, 255))

        # Channel branding at bottom
        brand_font_size = 28
        try:
            brand_font = ImageFont.truetype(font_paths[0], brand_font_size)
        except Exception:
            brand_font = font

        brand_text = "Stoic Modernized"
        brand_bbox = draw.textbbox((0, 0), brand_text, font=brand_font)
        brand_w = brand_bbox[2] - brand_bbox[0]
        brand_x = (thumb_width - brand_w) // 2
        brand_y = thumb_height - 80
        draw.text((brand_x + 2, brand_y + 2), brand_text, font=brand_font, fill=(0, 0, 0, 180))
        draw.text((brand_x, brand_y), brand_text, font=brand_font, fill=(212, 175, 55))  # Gold

        # Save as JPEG
        thumb_bg = thumb_bg.convert("RGB")
        thumb_bg.save(str(output_path), "JPEG", quality=90)
        return output_path

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

        raw_durations = []
        for scene in scenes:
            raw = float(scene.end_time - scene.start_time)
            raw_durations.append(max(0.1, raw))

        if audio_duration and audio_duration > 0:
            total_raw = sum(raw_durations)
            if total_raw > 0:
                scale = audio_duration / total_raw
                scaled = [max(0.8, duration * scale) for duration in raw_durations]
                adjustment = audio_duration - sum(scaled)
                scaled[-1] = max(0.8, scaled[-1] + adjustment)
                return scaled

        return [max(1.0, raw) for raw in raw_durations] or [3.0]



    def _output_duration_limit(self, audio_duration: Optional[float]) -> Optional[str]:
        if not audio_duration or audio_duration <= 0:
            return None
        return f"{audio_duration:.3f}"

    def _resolve_image_paths(self, scenes: list) -> list[Path]:
        image_dir = self.job_dir / "images"
        paths = []
        for scene in scenes:
            scene_number = scene.scene_number if hasattr(scene, "scene_number") else scene["scene_number"]
            path = image_dir / f"scene_{scene_number:03d}.jpg"
            if path.exists():
                paths.append(path)
        return paths

    def _escape_drawtext(self, text: str) -> str:
        return text.replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")

    def _build_endcard_drawtext(self, audio_duration: Optional[float]) -> str:
        endcard_text = self._escape_drawtext("subscribe to @stoic-modernized")
        start_time = max(0.0, (audio_duration or 0.0) - 3.0)
        return (
            "drawtext="
            f"text='{endcard_text}':"
            "fontcolor=white:fontsize=48:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            "box=1:boxcolor=black@0.45:boxborderw=24:"
            "x=(w-text_w)/2:y=(h-text_h)/2:"
            f"enable='gte(t,{start_time:.2f})'"
        )

    def _build_scene_clip_filter(self, *, width: int, height: int) -> str:
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"fps={self.fps},"
            "format=yuv420p"
        )

    def _render_zoom_frames(
        self,
        *,
        image_path: Path,
        frames_dir: Path,
        frames: int,
        width: int,
        height: int,
        target_zoom: float = 1.25,
    ) -> None:
        frames_dir.mkdir(parents=True, exist_ok=True)
        resample = getattr(Image, "Resampling", Image).LANCZOS

        with Image.open(image_path) as source_img:
            source = source_img.convert("RGB")
            src_w, src_h = source.size
            cover_scale = max(width / src_w, height / src_h)
            base_w = max(width, math.ceil(src_w * cover_scale))
            base_h = max(height, math.ceil(src_h * cover_scale))

            for frame_index in range(frames):
                progress = frame_index / max(1, frames - 1)
                zoom = 1.0 + ((target_zoom - 1.0) * progress)
                scaled_w = max(width, math.ceil(base_w * zoom))
                scaled_h = max(height, math.ceil(base_h * zoom))
                resized = source.resize((scaled_w, scaled_h), resample=resample)

                left = max(0, (scaled_w - width) // 2)
                top = max(0, (scaled_h - height) // 2)
                frame = resized.crop((left, top, left + width, top + height))
                frame.save(frames_dir / f"frame_{frame_index:06d}.jpg", quality=95)

    def _render_scene_clip(
        self,
        *,
        image_path: Path,
        output_path: Path,
        duration: float,
        width: int,
        height: int,
        animation_style: str,
    ) -> None:
        style = (animation_style or "zoom").lower()
        frames = max(2, int(round(duration * self.fps)))

        if style == "zoom":
            with tempfile.TemporaryDirectory(prefix="stoic-frames-") as temp_dir:
                frames_dir = Path(temp_dir)
                self._render_zoom_frames(
                    image_path=image_path,
                    frames_dir=frames_dir,
                    frames=frames,
                    width=width,
                    height=height,
                )
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-framerate",
                    str(self.fps),
                    "-i",
                    str(frames_dir / "frame_%06d.jpg"),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "slow",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    str(output_path),
                ]
                subprocess.run(cmd, capture_output=True, text=True, check=True)
            return

        filter_text = self._build_scene_clip_filter(width=width, height=height)
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(self.fps),
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            f"{duration:.3f}",
            "-vf",
            filter_text,
            "-r",
            str(self.fps),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)

    def _build_video_filter(
        self,
        *,
        subtitle_path: Optional[Path],
        add_short_endcard: bool,
        audio_duration: Optional[float],
    ) -> str:
        filter_chain = ["format=yuv420p"]
        if subtitle_path:
            filter_chain.append(f"subtitles={subtitle_path.as_posix()}")
        if add_short_endcard and audio_duration and audio_duration > 0:
            filter_chain.append(self._build_endcard_drawtext(audio_duration))
        return ",".join(filter_chain)

    def render_scene_sequence(
        self,
        scenes: list,
        images: list[Path],
        audio_path: Path,
        output_path: Path,
        durations: list[float],
        subtitle_path: Optional[Path] = None,
        width: int = 1920,
        height: int = 1080,
        add_short_endcard: bool = False,
        audio_duration: Optional[float] = None,
        background_music_path: Optional[Path] = None,
    ) -> subprocess.CompletedProcess:
        if not images:
            raise RuntimeError("No scene images found for rendering")

        clips_dir = self.output_dir / "scene_clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        clip_paths: list[Path] = []

        for index, (scene, image, duration) in enumerate(zip(scenes, images, durations, strict=False), start=1):
            clip_path = clips_dir / f"clip_{index:03d}.mp4"
            animation_style = getattr(scene, "animation_style", None) or (scene.get("animation_style") if isinstance(scene, dict) else "zoom") or "zoom"
            self._render_scene_clip(
                image_path=image,
                output_path=clip_path,
                duration=duration,
                width=width,
                height=height,
                animation_style=animation_style,
            )
            clip_paths.append(clip_path)

        concat_file = self.output_dir / "clips.txt"
        concat_file.write_text(
            "\n".join(f"file '{clip.as_posix()}'" for clip in clip_paths) + "\n",
            encoding="utf-8",
        )

        video_filter = self._build_video_filter(
            subtitle_path=subtitle_path,
            add_short_endcard=add_short_endcard,
            audio_duration=audio_duration,
        )
        duration_limit = self._output_duration_limit(audio_duration)

        logo_path = settings.watermark_logo_path
        has_logo = logo_path.exists()
        has_background_music = bool(background_music_path and background_music_path.exists())

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
        ]

        background_music_index: Optional[int] = None
        logo_index: Optional[int] = None

        if has_background_music and background_music_path is not None:
            background_music_index = 2
            cmd.extend(["-stream_loop", "-1", "-i", str(background_music_path)])

        if has_logo:
            logo_index = 3 if has_background_music else 2
            cmd.extend(["-i", str(logo_path)])

        needs_filter_complex = has_logo or has_background_music or bool(video_filter)

        if needs_filter_complex:
            filter_parts: list[str] = ["[0:v]format=yuv420p[v0]"]
            current_video = "v0"

            if has_logo and logo_index is not None:
                filter_parts.append(f"[{logo_index}:v]scale={settings.watermark_scale_width}:-1[wm]")
                filter_parts.append(
                    f"[{current_video}][wm]overlay=W-w-{settings.watermark_padding}:H-h-{settings.watermark_padding}[v1]"
                )
                current_video = "v1"

            if video_filter:
                filter_parts.append(f"[{current_video}]{video_filter}[vout]")
                current_video = "vout"

            audio_map = "1:a:0"
            if has_background_music and background_music_index is not None:
                filter_parts.append(
                    f"[{background_music_index}:a]volume={self.background_music_volume}[bgm]"
                )
                filter_parts.append("[1:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]")
                audio_map = "[aout]"

            cmd.extend([
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                f"[{current_video}]",
                "-map",
                audio_map,
            ])
        else:
            cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])

        cmd.extend([
            "-r",
            str(self.fps),
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-level:v",
            "4.1",
            "-preset",
            "slow",
            "-crf",
            "18",
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
        ])
        if duration_limit:
            cmd.extend(["-t", duration_limit])
        cmd.extend(["-shortest", str(output_path)])

        return subprocess.run(cmd, capture_output=True, text=True, check=True)
