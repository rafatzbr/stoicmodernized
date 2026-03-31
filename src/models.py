"""Pydantic models for the stoic-modernized pipeline."""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class JobStatus(str, Enum):
    """Status of a pipeline job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class ResearchSource(BaseModel):
    """A research source with relevance scoring."""

    title: str
    url: str
    note: str
    relevance: float = Field(ge=0.0, le=1.0)
    source: str  # e.g., article, video, book


class ResearchResult(BaseModel):
    """Results from the research stage."""

    title: str
    sources: list[ResearchSource] = Field(default_factory=list)
    key_insights: list[str] = Field(default_factory=list)
    workplace_applications: list[str] = Field(default_factory=list)


class Chapter(BaseModel):
    """A chapter with timestamp."""

    title: str
    timestamp: float  # in seconds


class Script(BaseModel):
    """Complete video script."""

    title: str
    hook: str  # Opening hook (first 15-30 seconds)
    narration: str  # Full voiceover text
    chapters: list[Chapter] = Field(default_factory=list)
    cta: str  # Call to action
    short_version: str = ""  # Shorts/Reels version
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Scene(BaseModel):
    """A scene in the video."""

    scene_number: int
    start_time: float  # in seconds
    end_time: float  # in seconds
    narration_segment: str
    visual_prompt: str
    text_overlay: Optional[str] = None
    animation_style: str = "zoom"  # zoom, pan, static, fade


class ScenePlan(BaseModel):
    """Scene plan for the video."""

    scenes: list[Scene] = Field(default_factory=list)
    intro_duration: float = 3.0
    outro_duration: float = 5.0
    total_duration: float = 0.0  # Will be calculated

    @model_validator(mode="after")
    def compute_total_duration(self) -> "ScenePlan":
        """Compute total duration from scenes plus intro/outro."""
        scene_duration = max((scene.end_time for scene in self.scenes), default=0.0)
        self.total_duration = scene_duration + self.intro_duration + self.outro_duration
        return self


class ImageAsset(BaseModel):
    """Generated image asset."""

    scene_number: int
    image_path: str
    prompt: str
    seed: Optional[int] = None


class SubtitleSegment(BaseModel):
    """A subtitle segment with timing."""

    start_time: float  # in seconds
    end_time: float  # in seconds
    text: str
    words: Optional[list[dict]] = None  # Optional per-word timing


class SubtitleResult(BaseModel):
    """Subtitle generation results."""

    srt_content: str
    segments: list[SubtitleSegment]
    srt_path: str
    json_path: str


class VideoRenderConfig(BaseModel):
    """Configuration for video rendering."""

    scenes: list[Scene]
    audio_path: str
    background_image_path: Optional[str] = None
    background_music_path: Optional[str] = None
    intro_image_path: Optional[str] = None
    outro_image_path: Optional[str] = None
    subtitle_path: str
    output_path: str


class VideoRenderResult(BaseModel):
    """Result of video rendering."""

    video_path: str
    duration: float
    thumbnail_path: Optional[str] = None


class YouTubeMetadata(BaseModel):
    """YouTube video metadata."""

    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    chapters: list[dict] = Field(default_factory=list)  # {"title": str, "timestamp": str}
    privacy_status: str = "unlisted"
    scheduled_publish_datetime: Optional[str] = None


class UploadResult(BaseModel):
    """Result of YouTube upload."""

    video_id: Optional[str] = None
    video_url: Optional[str] = None
    upload_status: str
    error: Optional[str] = None


class Job(BaseModel):
    """Pipeline job record."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # Stage outputs
    research_path: Optional[str] = None
    script_path: Optional[str] = None
    scene_plan_path: Optional[str] = None
    images_dir: Optional[str] = None
    audio_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    video_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    metadata_path: Optional[str] = None
    log_path: Optional[str] = None
