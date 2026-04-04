"""YouTube upload stage module."""

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
    ) -> UploadResult:
        """Upload video to YouTube.

        Args:
            video_path: Path to video file
            metadata: YouTube metadata (title, description, tags, etc.)
            thumbnail_path: Optional path to thumbnail

        Returns:
            UploadResult with upload status and video URL
        """
        if self.mock:
            return await self._mock_upload(video_path, metadata)
        else:
            return await self._real_upload(video_path, metadata, thumbnail_path)

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
        """Real YouTube upload using Google API.

        TODO: Implement using google-api-python-client

        This would:
        1. Initialize YouTube API client
        2. Upload video with metadata
        3. Upload thumbnail if provided
        4. Handle scheduling if datetime provided
        """
        if not self.api_key:
            return UploadResult(
                video_id=None,
                video_url=None,
                upload_status="failed",
                error="YouTube API key not configured",
            )

        # TODO: Implement real upload
        # from googleapiclient.discovery import build
        # from googleapiclient.http import MediaFileUpload

        # youtube = build("youtube", "v3", developerKey=self.api_key)

        # # Upload video
        # upload_response = youtube.videos().insert(
        #     part="snippet,status",
        #     body={
        #         "snippet": {
        #             "title": metadata["title"],
        #             "description": metadata["description"],
        #             "tags": metadata["tags"],
        #         },
        #         "status": {
        #             "privacyStatus": self.privacy_status,
        #         },
        #     },
        #     media_body=MediaFileUpload(video_path, chunksize=1024*1024, resumable=True),
        # ).execute()

        # # Upload thumbnail
        # if thumbnail_path:
        #     youtube.thumbnails().set(
        #         videoId=upload_response["id"],
        #         media_body=MediaFileUpload(thumbnail_path),
        #     ).execute()

        # return UploadResult(
        #     video_id=upload_response["id"],
        #     video_url=f"https://www.youtube.com/watch?v={upload_response['id']}",
        #     upload_status="completed",
        # )

        raise NotImplementedError("Real YouTube upload requires google-api-python-client")

    def generate_metadata(
        self,
        script_title: str,
        chapters: list[dict],
        description_template: Optional[str] = None,
    ) -> dict:
        """Generate YouTube metadata from script.

        Args:
            script_title: Video title from script
            chapters: List of chapter dicts with title and timestamp
            description_template: Optional description template

        Returns:
            Metadata dict ready for upload
        """
        # Generate tags based on title
        tags = self._generate_tags(script_title)

        # Format chapters for YouTube
        formatted_chapters = self._format_chapters(chapters)

        # Generate description
        description = self._generate_description(
            script_title, chapters, description_template
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
    ) -> str:
        """Generate video description.

        Args:
            title: Video title
            chapters: List of chapters
            template: Optional description template

        Returns:
            Formatted description string
        """
        if template:
            return template

        # Generate default description
        lines = [
            f"In this video, we explore {title.lower()}.",
            "",
            "What you'll learn:",
        ]

        for i, chapter in enumerate(chapters, 1):
            lines.append(f"{i}. {chapter.get('title', '')}")

        lines.extend([
            "",
            "Timestamps:",
        ])

        for chapter in chapters:
            timestamp = float(chapter.get("timestamp", 0) or 0)
            timestamp_str = f"{int(timestamp // 60):02d}:{int(timestamp % 60):02d}"
            lines.append(f"{timestamp_str} {chapter.get('title', '')}")

        lines.extend([
            "",
            f"Resources mentioned:",
            "• Meditations by Marcus Aurelius",
            "• Letters from a Stoic by Seneca",
            "• The Enchiridion by Epictetus",
            "",
            f"Subscribe to {settings.channel_name} for weekly videos on applying ancient wisdom to modern life.",
            "",
            "#stoicism #workplace #productivity #personaldevelopment #stoicmodernized",
        ])

        return "\n".join(lines)
