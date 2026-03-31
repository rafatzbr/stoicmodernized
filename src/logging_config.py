"""Logging configuration for the pipeline."""

import logging
import sys
from pathlib import Path
from typing import Optional

from src.config import settings


class JobLogger:
    """Logger for a specific job with file and console handlers."""

    def __init__(self, job_id: str, log_dir: Optional[Path] = None):
        """Initialize job-specific logger."""
        self.job_id = job_id
        self.log_dir = log_dir or settings.jobs_dir / job_id
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(f"stoic.{job_id}")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []  # Clear existing handlers

        # File handler
        log_file = self.log_dir / f"{job_id}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(self._get_formatter())
        self.logger.addHandler(file_handler)

        # Console handler (only if not running in background)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(console_handler)

        # Store log path for metadata
        self.log_path = str(log_file)

    def _get_formatter(self) -> logging.Formatter:
        """Get log formatter for file handlers."""
        return logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def debug(self, message: str) -> None:
        """Log debug message."""
        self.logger.debug(message)

    def info(self, message: str) -> None:
        """Log info message."""
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """Log warning message."""
        self.logger.warning(message)

    def error(self, message: str) -> None:
        """Log error message."""
        self.logger.error(message)

    def critical(self, message: str) -> None:
        """Log critical message."""
        self.logger.critical(message)


class PipelineLogger:
    """Global pipeline logger."""

    def __init__(self):
        """Initialize global pipeline logger."""
        self.logger = logging.getLogger("stoic.pipeline")
        self.logger.setLevel(logging.DEBUG)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
        )
        self.logger.addHandler(console_handler)

    def info(self, message: str) -> None:
        """Log info message."""
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """Log warning message."""
        self.logger.warning(message)

    def error(self, message: str) -> None:
        """Log error message."""
        self.logger.error(message)


# Global instances
pipeline_logger = PipelineLogger()
