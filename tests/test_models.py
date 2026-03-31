"""Tests for Pydantic models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models import (
    Chapter,
    ImageAsset,
    Job,
    JobStatus,
    ResearchResult,
    ResearchSource,
    Scene,
    ScenePlan,
    Script,
    SubtitleSegment,
    SubtitleResult,
    UploadResult,
    VideoRenderConfig,
    VideoRenderResult,
    YouTubeMetadata,
)


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """Should define all expected statuses."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.RETRYING.value == "retrying"


class TestResearchSource:
    """Tests for ResearchSource model."""

    def test_valid_source(self) -> None:
        """Should accept valid source data."""
        source = ResearchSource(
            title="Test Article",
            url="https://example.com",
            note="A test source",
            relevance=0.9,
            source="article",
        )

        assert source.title == "Test Article"
        assert source.relevance == 0.9
        assert source.source == "article"

    def test_relevance_range(self) -> None:
        """Should validate relevance is between 0 and 1."""
        # Valid
        source = ResearchSource(
            title="Test",
            url="https://example.com",
            note="Test",
            relevance=0.0,
            source="test",
        )
        assert source.relevance == 0.0

        source = ResearchSource(
            title="Test",
            url="https://example.com",
            note="Test",
            relevance=1.0,
            source="test",
        )
        assert source.relevance == 1.0

        # Invalid
        with pytest.raises(ValidationError):
            ResearchSource(
                title="Test",
                url="https://example.com",
                note="Test",
                relevance=-0.1,
                source="test",
            )

        with pytest.raises(ValidationError):
            ResearchSource(
                title="Test",
                url="https://example.com",
                note="Test",
                relevance=1.1,
                source="test",
            )


class TestResearchResult:
    """Tests for ResearchResult model."""

    def test_valid_result(self) -> None:
        """Should create valid research result."""
        result = ResearchResult(
            title="Test Topic",
            sources=[
                ResearchSource(
                    title="Source 1",
                    url="https://example.com/1",
                    note="Note 1",
                    relevance=0.9,
                    source="article",
                ),
            ],
            key_insights=["Insight 1", "Insight 2"],
            workplace_applications=["App 1"],
        )

        assert result.title == "Test Topic"
        assert len(result.sources) == 1
        assert len(result.key_insights) == 2
        assert len(result.workplace_applications) == 1


class TestChapter:
    """Tests for Chapter model."""

    def test_valid_chapter(self) -> None:
        """Should create valid chapter."""
        chapter = Chapter(title="Introduction", timestamp=0.0)

        assert chapter.title == "Introduction"
        assert chapter.timestamp == 0.0

    def test_chapter_with_timestamp(self) -> None:
        """Should handle non-zero timestamps."""
        chapter = Chapter(title="Section 1", timestamp=60.5)

        assert chapter.timestamp == 60.5


class TestScript:
    """Tests for Script model."""

    def test_valid_script(self) -> None:
        """Should create valid script."""
        script = Script(
            title="Test Video",
            hook="Welcome to the video",
            narration="Full narration text here.",
            chapters=[Chapter(title="Intro", timestamp=0.0)],
            cta="Please subscribe",
        )

        assert script.title == "Test Video"
        assert script.hook == "Welcome to the video"
        assert script.cta == "Please subscribe"
        assert len(script.chapters) == 1

    def test_script_with_short_version(self) -> None:
        """Should handle optional short version."""
        script = Script(
            title="Test",
            hook="Hook",
            narration="Narration",
            cta="CTA",
            short_version="Short version text",
        )

        assert script.short_version == "Short version text"

    def test_script_generates_timestamp(self) -> None:
        """Should generate generated_at timestamp."""
        script = Script(
            title="Test",
            hook="Hook",
            narration="Narration",
            cta="CTA",
        )

        assert isinstance(script.generated_at, datetime)


class TestScene:
    """Tests for Scene model."""

    def test_valid_scene(self) -> None:
        """Should create valid scene."""
        scene = Scene(
            scene_number=1,
            start_time=0.0,
            end_time=30.0,
            narration_segment="Test narration",
            visual_prompt="Test prompt",
        )

        assert scene.scene_number == 1
        assert scene.start_time == 0.0
        assert scene.end_time == 30.0
        assert scene.animation_style == "zoom"

    def test_scene_with_text_overlay(self) -> None:
        """Should handle optional text overlay."""
        scene = Scene(
            scene_number=1,
            start_time=0.0,
            end_time=30.0,
            narration_segment="Test",
            visual_prompt="Test",
            text_overlay="Key phrase",
        )

        assert scene.text_overlay == "Key phrase"


class TestScenePlan:
    """Tests for ScenePlan model."""

    def test_valid_plan(self) -> None:
        """Should create valid scene plan."""
        plan = ScenePlan(
            scenes=[
                Scene(
                    scene_number=1,
                    start_time=0.0,
                    end_time=30.0,
                    narration_segment="Test",
                    visual_prompt="Test",
                ),
            ],
        )

        assert len(plan.scenes) == 1
        assert plan.intro_duration == 3.0
        assert plan.outro_duration == 5.0

    def test_calculates_total_duration(self) -> None:
        """Should calculate total duration."""
        plan = ScenePlan(
            scenes=[
                Scene(
                    scene_number=1,
                    start_time=0.0,
                    end_time=60.0,
                    narration_segment="Test",
                    visual_prompt="Test",
                ),
            ],
            intro_duration=3.0,
            outro_duration=5.0,
        )

        # Total should include intro + scenes + outro
        assert plan.total_duration == 68.0


class TestImageAsset:
    """Tests for ImageAsset model."""

    def test_valid_asset(self) -> None:
        """Should create valid image asset."""
        asset = ImageAsset(
            scene_number=1,
            image_path="/path/to/image.jpg",
            prompt="Test prompt",
        )

        assert asset.scene_number == 1
        assert asset.image_path == "/path/to/image.jpg"

    def test_asset_with_seed(self) -> None:
        """Should handle optional seed."""
        asset = ImageAsset(
            scene_number=1,
            image_path="/path/to/image.jpg",
            prompt="Test",
            seed=42,
        )

        assert asset.seed == 42


class TestSubtitleSegment:
    """Tests for SubtitleSegment model."""

    def test_valid_segment(self) -> None:
        """Should create valid subtitle segment."""
        segment = SubtitleSegment(
            start_time=0.0,
            end_time=5.0,
            text="Hello world",
        )

        assert segment.start_time == 0.0
        assert segment.end_time == 5.0
        assert segment.text == "Hello world"

    def test_segment_with_words(self) -> None:
        """Should handle optional word timing."""
        segment = SubtitleSegment(
            start_time=0.0,
            end_time=5.0,
            text="Hello world",
            words=[
                {"word": "Hello", "start": 0.0, "end": 1.0},
                {"word": "world", "start": 1.0, "end": 2.0},
            ],
        )

        assert len(segment.words) == 2


class TestSubtitleResult:
    """Tests for SubtitleResult model."""

    def test_valid_result(self) -> None:
        """Should create valid subtitle result."""
        result = SubtitleResult(
            srt_content="1\n0:00:00,000 --> 0:00:05,000\nHello\n\n",
            segments=[
                SubtitleSegment(start_time=0.0, end_time=5.0, text="Hello"),
            ],
            srt_path="/path/to/subtitles.srt",
            json_path="/path/to/subtitles.json",
        )

        assert len(result.segments) == 1
        assert result.srt_path == "/path/to/subtitles.srt"


class TestVideoRenderConfig:
    """Tests for VideoRenderConfig model."""

    def test_valid_config(self) -> None:
        """Should create valid render config."""
        config = VideoRenderConfig(
            scenes=[
                Scene(
                    scene_number=1,
                    start_time=0.0,
                    end_time=30.0,
                    narration_segment="Test",
                    visual_prompt="Test",
                ),
            ],
            audio_path="/path/to/audio.wav",
            subtitle_path="/path/to/subs.srt",
            output_path="/path/to/output.mp4",
        )

        assert config.audio_path == "/path/to/audio.wav"
        assert config.output_path == "/path/to/output.mp4"

    def test_config_with_optional_paths(self) -> None:
        """Should handle optional paths."""
        config = VideoRenderConfig(
            scenes=[],
            audio_path="/audio.wav",
            background_image_path="/bg.jpg",
            background_music_path="/music.mp3",
            intro_image_path="/intro.jpg",
            outro_image_path="/outro.jpg",
            subtitle_path="/subs.srt",
            output_path="/output.mp4",
        )

        assert config.background_image_path == "/bg.jpg"


class TestVideoRenderResult:
    """Tests for VideoRenderResult model."""

    def test_valid_result(self) -> None:
        """Should create valid render result."""
        result = VideoRenderResult(
            video_path="/path/to/video.mp4",
            duration=300.0,
            thumbnail_path="/path/to/thumb.jpg",
        )

        assert result.video_path == "/path/to/video.mp4"
        assert result.duration == 300.0
        assert result.thumbnail_path == "/path/to/thumb.jpg"


class TestYouTubeMetadata:
    """Tests for YouTubeMetadata model."""

    def test_valid_metadata(self) -> None:
        """Should create valid metadata."""
        metadata = YouTubeMetadata(
            title="Test Video Title",
            description="Test description",
            tags=["tag1", "tag2"],
            chapters=[{"title": "Intro", "timestamp": 0}],
            privacy_status="unlisted",
        )

        assert metadata.title == "Test Video Title"
        assert len(metadata.tags) == 2
        assert metadata.privacy_status == "unlisted"

    def test_metadata_defaults(self) -> None:
        """Should have correct defaults."""
        metadata = YouTubeMetadata(
            title="Test",
            description="Test",
        )

        assert metadata.privacy_status == "unlisted"
        assert metadata.scheduled_publish_datetime is None
        assert metadata.tags == []


class TestUploadResult:
    """Tests for UploadResult model."""

    def test_successful_upload(self) -> None:
        """Should handle successful upload."""
        result = UploadResult(
            video_id="abc123",
            video_url="https://youtube.com/watch?v=abc123",
            upload_status="completed",
        )

        assert result.video_id == "abc123"
        assert result.upload_status == "completed"

    def test_failed_upload(self) -> None:
        """Should handle failed upload."""
        result = UploadResult(
            video_id=None,
            video_url=None,
            upload_status="failed",
            error="API key not configured",
        )

        assert result.error == "API key not configured"


class TestJob:
    """Tests for Job model."""

    def test_generates_job_id(self) -> None:
        """Should generate unique job ID."""
        job1 = Job(topic="Test 1")
        job2 = Job(topic="Test 2")

        assert job1.job_id != job2.job_id

    def test_default_status(self) -> None:
        """Should default to pending status."""
        job = Job(topic="Test")

        assert job.status == JobStatus.PENDING

    def test_default_timestamps(self) -> None:
        """Should generate default timestamps."""
        job = Job(topic="Test")

        assert isinstance(job.created_at, datetime)
        assert isinstance(job.updated_at, datetime)

    def test_optional_fields(self) -> None:
        """Should handle optional fields."""
        job = Job(
            topic="Test",
            error_message="Something went wrong",
        )

        assert job.error_message == "Something went wrong"
        assert job.started_at is None
        assert job.completed_at is None
