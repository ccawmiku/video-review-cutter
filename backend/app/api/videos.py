"""Video catalog API routes module.

Provides endpoints to trigger/inspect video scanning and list videos with filtering,
sorting by duration descending, and pagination.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.video import VideoStatus
from app.schemas.clip import (
    ClipSegmentCreate,
    ClipSegmentRead,
    ClipSegmentUpdate,
)
from app.schemas.decision import VideoDecisionRequest
from app.schemas.job import ProcessingJobCreate, ProcessingJobRead
from app.schemas.video import (
    DiscardRequest,
    ScanRequest,
    ScanStatusResponse,
    ScanSummary,
    VideoListResponse,
    VideoRead,
)
from app.services.catalog import catalog_service
from app.services.clip import clip_service
from app.services.discard import discard_service
from app.services.processing import processing_service
from app.services.streaming import streaming_service

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


@router.api_route(
    "/{video_id}/preview",
    methods=["GET", "HEAD"],
    summary="Stream video preview with HTTP Range support",
    description=(
        "Stream catalog video with single HTTP Range support (206/416), "
        "proper MIME and Content-Range headers, chunked streaming without whole-file buffering, "
        "and path safety validations."
    ),
)
@router.api_route(
    "/{video_id}/stream",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
async def preview_video(
    video_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Stream video preview by catalog video ID."""
    video = catalog_service.get_video_by_id(db=db, video_id=video_id)
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video with id {video_id} not found",
        )
    return await streaming_service.stream_video_preview(
        video=video,
        request=request,
    )


@router.get(
    "/{video_id}/clips",
    response_model=list[ClipSegmentRead],
    summary="List ordered clip segments for a video",
)
def list_video_clips(
    video_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[ClipSegmentRead]:
    """Retrieve all clip segments associated with video ordered sequentially."""
    clips = clip_service.list_clips(db=db, video_id=video_id)
    return [ClipSegmentRead.model_validate(clip) for clip in clips]


@router.post(
    "/{video_id}/clips",
    response_model=ClipSegmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new clip segment for a video",
)
def create_video_clip(
    video_id: int,
    payload: ClipSegmentCreate,
    db: Annotated[Session, Depends(get_db)],
) -> ClipSegmentRead:
    """Create a new clip segment validating start, end, and duration bounds."""
    clip = clip_service.create_clip(db=db, video_id=video_id, payload=payload)
    return ClipSegmentRead.model_validate(clip)


@router.get(
    "/{video_id}/clips/{clip_id}",
    response_model=ClipSegmentRead,
    summary="Get a specific clip segment by ID",
)
def get_video_clip(
    video_id: int,
    clip_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> ClipSegmentRead:
    """Retrieve details of a single clip segment belonging to the video."""
    clip = clip_service.get_clip_or_404(db=db, video_id=video_id, clip_id=clip_id)
    return ClipSegmentRead.model_validate(clip)


@router.put(
    "/{video_id}/clips/{clip_id}",
    response_model=ClipSegmentRead,
    summary="Update an existing clip segment",
)
@router.patch(
    "/{video_id}/clips/{clip_id}",
    response_model=ClipSegmentRead,
    include_in_schema=False,
)
def update_video_clip(
    video_id: int,
    clip_id: int,
    payload: ClipSegmentUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> ClipSegmentRead:
    """Update clip segment properties and validate time range bounds."""
    clip = clip_service.update_clip(db=db, video_id=video_id, clip_id=clip_id, payload=payload)
    return ClipSegmentRead.model_validate(clip)


@router.delete(
    "/{video_id}/clips/{clip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a clip segment",
)
def delete_video_clip(
    video_id: int,
    clip_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Delete a clip segment from the video."""
    clip_service.delete_clip(db=db, video_id=video_id, clip_id=clip_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.api_route(
    "/{video_id}/decision",
    methods=["POST", "PUT"],
    response_model=VideoRead,
    summary="Record explicit review decision for a video",
    description=(
        "Explicitly records review decision: 'no_action' (requires 0 clip segments) "
        "or 'clip_selected' (requires at least 1 clip segment). "
        "Updates video status and timestamps idempotently."
    ),
)
def record_video_decision(
    video_id: int,
    payload: VideoDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
) -> VideoRead:
    """Record explicit review decision on video with idempotence."""
    video = clip_service.record_decision(db=db, video_id=video_id, decision=payload.decision_value)
    return VideoRead.model_validate(video)


@router.api_route(
    "/{video_id}/discard",
    methods=["POST", "PUT"],
    response_model=VideoRead,
    summary="Safely move video to discarded storage and mark as discarded",
    description=(
        "Safely moves video file from configured VIDEO_ROOTS into DISCARDED_DIR without "
        "deleting, avoids filename collisions deterministically, and updates status to 'discarded' "
        "only after move verification."
    ),
)
def discard_video(
    video_id: int,
    db: Annotated[Session, Depends(get_db)],
    payload: DiscardRequest | None = None,
) -> VideoRead:
    """Safely discard catalog video."""
    reason = payload.reason if payload else None
    video = discard_service.discard_video(db=db, video_id=video_id, reason=reason)
    return VideoRead.model_validate(video)


@router.post(
    "/{video_id}/process",
    response_model=ProcessingJobRead,
    summary="Start background clip processing and archive replacement job",
    description=(
        "Enqueues or runs a persistent processing job for the video with its validated "
        "ClipSegments. Enforces idempotency: rejects duplicate active jobs. "
        "Renders clips in order, prefers safe stream-copy concat with fallback to "
        "H.264/AAC re-encode, validates non-empty temp output, safely moves original "
        "to ARCHIVE_DIR, atomically replaces original path, and updates status to "
        "'replaced' only upon full success."
    ),
)
@router.post(
    "/{video_id}/jobs",
    response_model=ProcessingJobRead,
    include_in_schema=False,
)
def process_video(
    video_id: int,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    payload: ProcessingJobCreate | None = None,
    background: Annotated[bool, Query(description="Run asynchronously in background")] = True,
) -> ProcessingJobRead:
    """Create and trigger video processing job."""
    force_reencode = payload.force_reencode if payload else False
    job = processing_service.create_job(
        db=db,
        video_id=video_id,
        force_reencode=force_reencode,
    )
    if background:
        background_tasks.add_task(processing_service.run_job, job.id)
    else:
        job = processing_service.run_job(job_id=job.id, db=db)
    return ProcessingJobRead.model_validate(job)


@router.get(
    "/{video_id}/jobs",
    response_model=list[ProcessingJobRead],
    summary="List all processing jobs for a video",
)
def list_video_jobs(
    video_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[ProcessingJobRead]:
    """Retrieve all processing jobs for a video ordered newest first."""
    jobs = processing_service.list_jobs_for_video(db=db, video_id=video_id)
    return [ProcessingJobRead.model_validate(job) for job in jobs]


@router.get(
    "/{video_id}/jobs/latest",
    response_model=ProcessingJobRead | None,
    summary="Get the most recent processing job for a video",
)
def get_latest_video_job(
    video_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> ProcessingJobRead | None:
    """Retrieve the latest processing job for a video."""
    job = processing_service.get_latest_job_for_video(db=db, video_id=video_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No processing jobs found for video {video_id}",
        )
    return ProcessingJobRead.model_validate(job)


@router.get(
    "/{video_id}/jobs/{job_id}",
    response_model=ProcessingJobRead,
    summary="Get details of a specific processing job",
)
def get_video_job(
    video_id: int,
    job_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> ProcessingJobRead:
    """Retrieve a specific processing job by ID."""
    job = processing_service.get_job(db=db, job_id=job_id)
    if job.video_id != video_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} does not belong to video {video_id}",
        )
    return ProcessingJobRead.model_validate(job)


@router.post(
    "/{video_id}/jobs/{job_id}/cancel",
    response_model=ProcessingJobRead,
    summary="Cancel a pending or running processing job",
)
def cancel_video_job(
    video_id: int,
    job_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> ProcessingJobRead:
    """Cancel a pending or running processing job."""
    job = processing_service.get_job(db=db, job_id=job_id)
    if job.video_id != video_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} does not belong to video {video_id}",
        )
    cancelled_job = processing_service.cancel_job(db=db, job_id=job_id)
    return ProcessingJobRead.model_validate(cancelled_job)

