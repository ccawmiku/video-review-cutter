"""Core application configuration module.

Loads configuration from environment variables with safe defaults.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field


def _parse_list_from_env(val: str | None, default: list[str]) -> list[str]:
    """Parse comma/semicolon-separated string or JSON string into list of strings."""
    if not val:
        return default
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
    delimiter = ";" if ";" in val else ","
    return [item.strip() for item in val.split(delimiter) if item.strip()]


class Settings(BaseModel):
    """Application settings schema."""

    host: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))

    # Video storage directories
    # VIDEO_ROOTS: Semicolon or comma-separated source directories containing videos
    video_roots: list[str] = Field(
        default_factory=lambda: _parse_list_from_env(
            os.getenv("VIDEO_ROOTS"), ["/media/videos", "./mock_media/videos"]
        )
    )
    # ARCHIVE_DIR: Destination directory for preserved/approved video files
    archive_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("ARCHIVE_DIR", "./data/archive"))
    )
    # DISCARDED_DIR: Destination directory for rejected/discarded video files
    discarded_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("DISCARDED_DIR", "./data/discarded"))
    )

    # Database configuration (SQLite placeholder)
    database_url: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./data/video_review.db")
    )

    # FFmpeg executable paths
    ffmpeg_path: str = Field(default_factory=lambda: os.getenv("FFMPEG_PATH", "ffmpeg"))
    ffprobe_path: str = Field(default_factory=lambda: os.getenv("FFPROBE_PATH", "ffprobe"))

    # CORS origins
    cors_origins: list[str] = Field(
        default_factory=lambda: _parse_list_from_env(
            os.getenv("CORS_ORIGINS"),
            ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:80"],
        )
    )


settings = Settings()
