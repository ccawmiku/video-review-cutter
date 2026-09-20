"""Video catalog Pydantic schemas module."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.video import VideoStatus


class VideoBase(BaseModel):
    """Base fields for video records."""

    path: str
    filename: str
    size: int
    duration: float | None = None
    status: VideoStatus = VideoStatus.UNPROCESSED
    width: int | None = None
    height: int | None = None
    codec: str | None = None
    fps: float | None = None
    bit_rate: int | None = None
    scan_error: str | None = None
    scan_metadata: dict[str, Any] | None = None


class VideoRead(VideoBase):
    """Schema for returning video details from API."""

    id: int
    created_at: datetime
    updated_at: datetime
    last_scanned_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VideoListResponse(BaseModel):
    """Paginated list of videos sorted by duration descending."""

    items: list[VideoRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class ScanSummary(BaseModel):
    """Execution summary for a completed video scan run."""

    total_found: int = Field(description="Total video files discovered during scan")
    added: int = Field(description="Number of newly inserted video records")
    updated: int = Field(description="Number of existing video records updated")
    failed: int = Field(description="Number of videos where probe extraction failed")
    missing_roots: list[str] = Field(
        default_factory=list, description="Configured roots that do not exist"
    )
    scanned_roots: list[str] = Field(
        default_factory=list, description="Directories traversed during scan"
    )
    duration_seconds: float = Field(description="Elapsed seconds taken to execute scan")
    started_at: datetime
    finished_at: datetime


class ScanStatusResponse(BaseModel):
    """Inspection response for video catalog scan status."""

    has_scanned: bool = Field(description="Whether at least one scan has been executed")
    last_scan: ScanSummary | None = Field(
        default=None, description="Summary details of most recent scan"
    )


class ScanRequest(BaseModel):
    """Optional payload to trigger scan on custom or configured roots."""

    roots: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of root directories to scan. Defaults to configured VIDEO_ROOTS."
        ),
    )
