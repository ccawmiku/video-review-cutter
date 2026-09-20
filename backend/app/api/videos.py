"""Video catalog API routes module.

Provides endpoints to trigger/inspect video scanning and list videos with filtering,
sorting by duration descending, and pagination.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.video import VideoStatus
from app.schemas.video import (
    ScanRequest,
    ScanStatusResponse,
    ScanSummary,
    VideoListResponse,
    VideoRead,
)
from app.services.catalog import catalog_service

router = APIRouter()


@router.post(
    "/scan",
    response_model=ScanSummary,
    summary="Trigger video directory scan",
    description=(
        "Recursively scans configured or requested video roots, probes media metadata, "
        "and upserts records into the SQLite database. Preserves review statuses and does not "
        "delete rows on probe errors."
    ),
)
def trigger_scan(
    db: Annotated[Session, Depends(get_db)],
    payload: ScanRequest | None = None,
) -> ScanSummary:
    """Trigger recursive catalog scan."""
    roots = payload.roots if payload else None
    return catalog_service.scan(db=db, roots=roots)


@router.get(
    "/scan/status",
    response_model=ScanStatusResponse,
    summary="Inspect latest scan execution status",
)
def get_scan_status() -> ScanStatusResponse:
    """Inspect latest scan run summary."""
    summary = catalog_service.last_scan_summary
    return ScanStatusResponse(
        has_scanned=summary is not None,
        last_scan=summary,
    )


@router.get(
    "",
    response_model=VideoListResponse,
    summary="List catalog videos",
    description=(
        "Retrieve paginated videos sorted by duration descending with optional status filtering."
    ),
)
def list_videos(
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[
        VideoStatus | None,
        Query(
            description=(
                "Filter by status: unprocessed, no_action, clip_selected, replaced, discarded"
            )
        ),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 50,
    sort_by: Annotated[
        str, Query(description="Sort field: duration, size, created_at")
    ] = "duration",
    order: Annotated[str, Query(description="Sort order: desc, asc")] = "desc",
) -> VideoListResponse:
    """List videos sorted by duration descending with status filtering and pagination."""
    return catalog_service.list_videos(
        db=db,
        status=status,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
    )


@router.get(
    "/{video_id}",
    response_model=VideoRead,
    summary="Get video details by ID",
)
def get_video(
    video_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> VideoRead:
    """Retrieve details of a specific video record."""
    video = catalog_service.get_video_by_id(db=db, video_id=video_id)
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video with id {video_id} not found",
        )
    return VideoRead.model_validate(video)
