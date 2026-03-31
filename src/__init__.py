"""Stoic Modernized - Automated YouTube video creation for Stoicism channel."""

__version__ = "0.1.0"
__author__ = "Rafael Tz"

from src.config import settings
from src.database import db
from src.logging_config import JobLogger, pipeline_logger
from src.utils import ensure_dir, ensure_file_dir, get_job_dir, save_json, load_json

__all__ = [
    "settings",
    "db",
    "JobLogger",
    "pipeline_logger",
    "ensure_dir",
    "ensure_file_dir",
    "get_job_dir",
    "save_json",
    "load_json",
]
