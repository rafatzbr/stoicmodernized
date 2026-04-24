"""YouTube upload stage module."""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional

from src.config import settings
from src.models import UploadResult


class YouTubeUploader:
    """Handles YouTube video upload."""

    def __init__(self, api_key: Optional[str] = None, mock: bool = False):
        """Initialize YouTube uploader.

        Args:
            api_key: YouTube Data API key (from env or settings)
            mock: If True, use mock upload
        """
        self.api_key = api_key or settings.youtube_api_key
        self.mock = mock or settings.mock_mode
        self.privacy_status = settings.youtube_privacy_status.value
        self.schedule_datetime = settings.youtube_schedule_datetime

    async def upload(
        self,
        video_path: str,
        metadata: dict,
        thumbnail_path: Optional[str] = None,
        job_dir: Optional[str] = None,
    ) -> UploadResult:
        """Upload video to YouTube.

        Args:
            video_path: Path to video file
            metadata: YouTube metadata (title, description, tags, etc.)
            thumbnail_path: Optional path to thumbnail

        Returns:
            UploadResult with upload status and video URL
        """
        guardrail_error = self._background_music_guardrail(job_dir)
        if guardrail_error:
            return UploadResult(
                video_id=None,
                video_url=None,
                upload_status="blocked",
                error=guardrail_error,
            )

        if self.mock:
            return await self._mock_upload(video_path, metadata)
        else:
            return await self._real_upload(video_path, metadata, thumbnail_path)

    def _background_music_guardrail(self, job_dir: Optional[str]) -> Optional[str]:
        if settings.youtube_allow_background_music_uploads:
            return None
        if not job_dir:
            return None

        job_dir_path = Path(job_dir)
        render_manifest_path = job_dir_path / "render_manifest.json"
        if render_manifest_path.exists():
            try:
                render_manifest = json.loads(render_manifest_path.read_text())
                if not render_manifest.get("background_music_included"):
                    return None
            except Exception:
                pass

        audio_dir = job_dir_path / "audio"
        if not audio_dir.exists():
            return None

        music_files = [
            audio_dir / "background_music.mp3",
            audio_dir / "background_music.wav",
            audio_dir / "background_music.ogg",
            audio_dir / "background_music.m4a",
        ]
        has_background_music = any(path.exists() for path in music_files)
        if not has_background_music:
            return None

        details = ""
        metadata_path = audio_dir / "background_music.json"
        if metadata_path.exists():
            try:
                payload = json.loads(metadata_path.read_text())
                track = payload.get("track") or {}
                title = track.get("title") or "unknown"
                artist = track.get("artist") or "unknown"
                provider = payload.get("provider") or "unknown"
                approved = bool(payload.get("approved_for_youtube"))
                instrumental = bool(payload.get("instrumental"))
                low_background = bool(payload.get("low_background"))
                if provider == "curated" and approved and instrumental and low_background:
                    return None
                details = f" Detected track: {title} by {artist} ({provider})."
            except Exception:
                pass

        return (
            "Upload blocked by music safety guardrail: background music is present but not from the approved curated library." + details +
            " Remove the background track or replace it with a curated approved instrumental track."
        )

    async def _mock_upload(
        self, video_path: str, metadata: dict
    ) -> UploadResult:
        """Mock video upload."""
        return UploadResult(
            video_id="dQw4w9WgXcQ",
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            upload_status="completed",
            error=None,
        )

    async def _real_upload(
        self,
        video_path: str,
        metadata: dict,
        thumbnail_path: Optional[str] = None,
    ) -> UploadResult:
        """Real YouTube upload using Google API with OAuth2.

        Uses OAuth2 authentication for user authorization to upload videos.
        """
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            # Try to load OAuth2 credentials from file
            creds = None
            token_path = Path(os.path.expanduser("~/.stoic-modernized/oauth2_token.json"))
            credentials_file = settings.youtube_credentials_path

            # Load existing credentials if available
            if token_path.exists():
                try:
                    creds = Credentials.from_authorized_user_file(str(token_path), scopes=["https://www.googleapis.com/auth/youtube.upload"])
                except Exception as e:
                    print(f"[yellow]Existing token invalid, re-authenticating...[/yellow]")

            # If no valid credentials, show auth instructions
            if not creds and not settings.youtube_api_key:
                return UploadResult(
                    video_id=None,
                    video_url=None,
                    upload_status="failed",
                    error="No OAuth2 token found. Run: python -m src.auth_oauth",
                )

            # Build YouTube API client
            youtube = build("youtube", "v3", credentials=creds if creds else None)

            # Prepare video metadata
            video_body = {
                "snippet": {
                    "title": metadata.get("title", "Untitled Video"),
                    "description": metadata.get("description", ""),
                    "tags": metadata.get("tags", []),
                    "categoryId": "22",  # People & Blogs
                },
                "status": {
                    "privacyStatus": self.privacy_status,
                    "selfDeclaredMadeForKids": False,
                },
            }

            # Add scheduling if datetime provided
            if self.schedule_datetime:
                from datetime import datetime
                try:
                    schedule_time = datetime.fromisoformat(self.schedule_datetime.replace("Z", "+00:00"))
                    video_body["status"]["uploadStatus"] = "scheduled"
                    video_body["status"]["publishAt"] = schedule_time.isoformat()
                except Exception as e:
                    print(f"[yellow]Invalid schedule datetime, publishing immediately:[/yellow] {e}")

            # Upload video with resumable upload
            print(f"[dim]Uploading video: {video_path}[/dim]")
            media = MediaFileUpload(
                video_path,
                chunksize=1024 * 1024 * 10,  # 10MB chunks for faster uploads
                resumable=True
            )

            response = (
                youtube.videos()
                .insert(
                    part="snippet,status",
                    body=video_body,
                    media_body=media
                )
                .execute()
            )

            video_id = response["id"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            print(f"[green]✓ Video uploaded: {video_url}[/green]")

            # Upload thumbnail if provided
            if thumbnail_path and os.path.exists(thumbnail_path):
                print(f"[dim]Uploading thumbnail: {thumbnail_path}[/dim]")
                try:
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(thumbnail_path)
                    ).execute()
                    print(f"[green]✓ Thumbnail uploaded[/green]")
                except Exception as e:
                    print(f"[yellow]✗ Thumbnail upload failed: {e}[/yellow]")

            return UploadResult(
                video_id=video_id,
                video_url=video_url,
                upload_status="completed",
                error=None,
            )

        except Exception as e:
            error_msg = str(e)
            print(f"[red]✗ Upload failed: {error_msg}[/red]")

            # Check for specific error types
            if "invalid_grant" in error_msg or "unauthorized" in error_msg.lower():
                return UploadResult(
                    video_id=None,
                    video_url=None,
                    upload_status="failed",
                    error="OAuth2 token expired. Run: python -m src.auth_oauth",
                )

            return UploadResult(
                video_id=None,
                video_url=None,
                upload_status="failed",
                error=error_msg,
            )

    def generate_metadata(
        self,
        script_title: str,
        chapters: list[dict],
        description_template: Optional[str] = None,
        script_text: Optional[str] = None,
    ) -> dict:
        """Generate YouTube metadata from script.

        Args:
            script_title: Video title from script
            chapters: List of chapter dicts with title and timestamp
            description_template: Optional description template
            script_text: Optional full script narration for AI description generation

        Returns:
            Metadata dict ready for upload
        """
        # Generate tags based on title
        tags = self._generate_tags(script_title)

        # Format chapters for YouTube
        formatted_chapters = self._format_chapters(chapters)

        # Generate description (AI-generated if script_text provided, else fallback)
        description = self._generate_description(
            script_title, chapters, description_template, script_text
        )

        return {
            "title": f"{script_title} | {settings.channel_name}",
            "description": description,
            "tags": tags,
            "chapters": formatted_chapters,
            "privacy_status": self.privacy_status,
            "scheduled_publish_datetime": self.schedule_datetime,
        }

    def _generate_tags(self, title: str) -> list[str]:
        """Generate tags based on video title.

        Args:
            title: Video title

        Returns:
            List of tags
        """
        base_tags = [
            "stoicism",
            "stoic philosophy",
            "modern stoicism",
            "stoic modernized",
            "ancient wisdom",
            "personal development",
            "mindfulness",
            "productivity",
            "career advice",
            "workplace stress",
        ]

        # Extract keywords from title
        words = title.lower().split()
        keyword_tags = []

        for word in words:
            if len(word) > 4 and word not in ["the", "and", "for", "how", "what"]:
                keyword_tags.append(word)

        return base_tags + keyword_tags[:5]

    def _format_chapters(self, chapters: list[dict]) -> list[dict]:
        """Format chapters for YouTube metadata.

        Args:
            chapters: List of chapter dicts

        Returns:
            Formatted chapters for YouTube
        """
        return [
            {
                "title": chapter.get("title", ""),
                "timestamp": chapter.get("timestamp", 0),
            }
            for chapter in chapters
        ]

    def _generate_description(
        self,
        title: str,
        chapters: list[dict],
        template: Optional[str] = None,
        script_text: Optional[str] = None,
    ) -> str:
        """Generate video description.

        Args:
            title: Video title
            chapters: List of chapters
            template: Optional description template
            script_text: Optional full script text for AI-generated description

        Returns:
            Formatted description string
        """
        if template:
            return template

        # Try to use AI to generate description if script text is available
        if script_text:
            ai_description = self._generate_description_with_ai(title, chapters, script_text)
            if ai_description:
                return ai_description

        # Fallback to default description
        return self._generate_default_description(title, chapters)

    def _generate_default_description(self, title: str, chapters: list[dict]) -> str:
        """Generate a default description when AI fails or isn't available."""
        return f"""In this video, we explore {title.lower()}.

Subscribe to Stoic Modernized for practical Stoic tools you can use at work.

Resources:
Meditations by Marcus Aurelius https://amzn.to/3Na3Yrw
Letters from a Stoic by Seneca https://amzn.to/40km3Gj
Discourses and Enchiridion https://amzn.to/40VhlyR

#stoicism #stoicmodernized #workplace #personaldevelopment"""

    def _generate_description_with_ai(
        self,
        title: str,
        chapters: list[dict],
        script_text: str,
    ) -> Optional[str]:
        """Generate description using local LLM based on script content.

        Args:
            title: Video title
            chapters: List of chapters with timestamps
            script_text: Full script narration text

        Returns:
            AI-generated description or None if generation fails
        """
        # Extract the hook (first paragraph or first ~150 chars)
        hook = ""
        if "\n\n" in script_text:
            hook = script_text.split("\n\n")[0][:200]
        elif len(script_text) > 200:
            hook = script_text[:200]
        else:
            hook = script_text

        prompt = f"""You are a YouTube description writer for the Stoic Modernized channel. Write a very short, hook-driven description (max 50 words total).

Video Title: {title}

Hook from video: {hook}

Write a description that:
1. Opens with 1-2 sentences expanding on the hook (make it engaging)
2. Ends with: "Subscribe to Stoic Modernized for practical Stoic tools you can use at work."
3. Add hashtags at the end: #stoicism #stoicmodernized #workplace

Keep it extremely tight. No bullet points. No timestamps. No filler. Output only the description text."""

        try:
            import requests

            payload = {
                "model": settings.local_script_model or settings.local_llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You write very short, hook-driven YouTube descriptions. Max 50 words. No bullet points. No timestamps. No filler. Output plain text only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 200,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            response = requests.post(
                settings.local_llm_base_url,
                json=payload,
                timeout=settings.local_llm_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            content = self._extract_message_content(data)

            if content and content.strip():
                # Clean up any markdown artifacts
                content = re.sub(r"```(?:description)?\s*", "", content, flags=re.IGNORECASE)
                content = re.sub(r"\s*```\s*$", "", content, flags=re.IGNORECASE)
                content = content.strip()
                
                # Add affiliate links before any hashtags
                content = self._add_affiliate_links(content)
                return content

            return None

        except Exception as e:
            print(f"[yellow]⚠ AI description generation failed: {type(e).__name__}. Using fallback.[/yellow]")
            return None

    def _add_affiliate_links(self, description: str) -> str:
        """Append affiliate links after hashtags in description."""
        affiliate_links = """

Resources:
Meditations by Marcus Aurelius https://amzn.to/3Na3Yrw
Letters from a Stoic by Seneca https://amzn.to/40km3Gj
Discourses and Enchiridion https://amzn.to/40VhlyR"""
        
        # Just append links at the end
        return f"{description}{affiliate_links}"

    def _extract_message_content(self, data: dict) -> str:
        """Extract message content from LLM response."""
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text") or ""))
            return "\n".join(part for part in text_parts if part)
        return ""
