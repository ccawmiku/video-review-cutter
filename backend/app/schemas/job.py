"""Processing job Pydantic schemas module."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.job import JobStatus


class ProcessingJobRead(BaseModel):
    """Schema for returning processing job details."""

    id: int
    video_id: int
    status: JobStatus
    progress: float = Field(ge=0.0, le=1.0)
    message: str | None = None
    error: str | None = None
    strategy: str | None = None
    output_path: str | None = None
    archive_path: str | None = None
    job_metadata: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcessingJobCreate(BaseModel):
    """Payload to trigger a processing job."""

    force_reencode: bool = Field(
        default=False,
        description="Force full re-encode even if stream-copy concat might be compatible",
    )


class ProcessingJobListResponse(BaseModel):
    """List response for video processing jobs."""

    jobs: list[ProcessingJobRead]
    total: int
