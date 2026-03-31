"""Database module for job tracking using SQLite."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


class JobRecord(Base):
    """SQLAlchemy model for pipeline jobs."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    topic: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Stage outputs (stored as JSON)
    research_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    script_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    scene_plan_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    images_dir: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    audio_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subtitle_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    video_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    log_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Database:
    """Database manager for job tracking."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database connection."""
        self.db_path = db_path or settings.db_path
        self.engine = create_engine(settings.db)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        """Get a database session."""
        return self.SessionLocal()

    def create_job(self, topic: str) -> JobRecord:
        """Create a new job record."""
        import uuid

        session = self.get_session()
        try:
            job_id = str(uuid.uuid4())
            job = JobRecord(
                job_id=job_id,
                topic=topic,
                status="pending",
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            return job
        finally:
            session.close()

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Get a job by ID."""
        session = self.get_session()
        try:
            return session.query(JobRecord).filter(JobRecord.job_id == job_id).first()
        finally:
            session.close()

    def update_job(self, job_id: str, **kwargs) -> Optional[JobRecord]:
        """Update a job record."""
        session = self.get_session()
        try:
            job = session.query(JobRecord).filter(JobRecord.job_id == job_id).first()
            if job:
                for key, value in kwargs.items():
                    if hasattr(job, key):
                        setattr(job, key, value)
                session.commit()
                session.refresh(job)
                return job
            return None
        finally:
            session.close()

    def get_all_jobs(self, status: Optional[str] = None) -> list[JobRecord]:
        """Get all jobs, optionally filtered by status."""
        session = self.get_session()
        try:
            query = session.query(JobRecord)
            if status:
                query = query.filter(JobRecord.status == status)
            return query.order_by(JobRecord.created_at.desc()).all()
        finally:
            session.close()

    def delete_job(self, job_id: str) -> bool:
        """Delete a job record."""
        session = self.get_session()
        try:
            job = session.query(JobRecord).filter(JobRecord.job_id == job_id).first()
            if job:
                session.delete(job)
                session.commit()
                return True
            return False
        finally:
            session.close()


# Global database instance
db = Database()
