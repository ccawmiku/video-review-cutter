"""Video clip processing and archive replacement domain service.

Coordinates the end-to-end bounded processing workflow:
1. Validates video, ClipSegments, source path, and destination roots.
2. Creates and manages persistent ProcessingJob lifecycle with idempotency checks.
3. Renders ordered segments to a temporary output in the original directory using
   injectable FFmpeg runner (prefers stream-copy concat, falls back to H.264/AAC).
4. Validates that rendered temporary file is a non-empty regular file.
5. Moves original video file to configured ARCHIVE_DIR with collision-safe name.
6. Atomically replaces original path with rendered file.
7. Updates Video status to 'replaced' only after every filesystem and DB step succeeds.
8. On failure, preserves original and DB state, cleans up temp files, and records failed job.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.job import JobStatus, ProcessingJob
from app.models.video import Video, VideoStatus, utc_now
from app.services.discard import (
    get_collision_free_destination,
    is_subpath,
    move_file_safely,
)
from app.services.ffmpeg_runner import (
    FFmpegCommandBuilder,
    FFmpegRunner,
    SubprocessFFmpegRunner,
    render_segments_pipeline,
)

logger = logging.getLogger(__name__)


class ProcessingService:
    """Domain service managing the clip processing and archive replacement workflow."""

    def __init__(
        self,
        runner: FFmpegRunner | None = None,
        command_builder: FFmpegCommandBuilder | None = None,
        archive_dir: Path | None = None,
        video_roots: list[str] | None = None,
    ) -> None:
        self.runner: FFmpegRunner = runner or SubprocessFFmpegRunner()
        self.command_builder: FFmpegCommandBuilder = command_builder or FFmpegCommandBuilder()
        self._custom_archive_dir = archive_dir
        self._custom_video_roots = video_roots

    @property
    def archive_dir(self) -> Path:
        """Effective archive directory."""
        return self._custom_archive_dir or settings.archive_dir

    @property
    def video_roots(self) -> list[str]:
        """Effective video root paths."""
        return self._custom_video_roots or settings.video_roots

    def validate_source_file(
        self,
        source_path: Path,
        allowed_roots: list[str] | None = None,
    ) -> Path:
        """Validate source video path against configured VIDEO_ROOTS and regular file checks."""
        if not source_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source video file not found on disk: {source_path}",
            )

        if not source_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Source path is not a regular file: {source_path}",
            )

        try:
            resolved_source = source_path.resolve(strict=True)
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unable to resolve source video path: {err}",
            ) from err

        if not resolved_source.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Resolved source path is not a regular file",
            )

        root_candidates = allowed_roots if allowed_roots is not None else self.video_roots
        valid_roots: list[Path] = []
        for r in root_candidates:
            try:
                rp = Path(r).expanduser().resolve()
                if rp.exists() and rp.is_dir():
                    valid_roots.append(rp)
            except Exception:
                continue

        if not valid_roots:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: no valid configured video roots available",
            )

        raw_in_root = any(is_subpath(source_path.absolute(), root) for root in valid_roots)
        resolved_in_root = any(is_subpath(resolved_source, root) for root in valid_roots)

        if source_path.is_symlink() and not resolved_in_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: symlink escape outside configured video roots",
            )

        if not raw_in_root or not resolved_in_root:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: video path outside configured video roots",
            )

        return resolved_source

    def validate_destination_root(self, custom_archive_dir: Path | None = None) -> Path:
        """Validate and create ARCHIVE_DIR directory."""
        dest_dir = (custom_archive_dir or self.archive_dir).expanduser()
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create destination archive directory: {err}",
            ) from err

        resolved_dest_dir = dest_dir.resolve()
        if not resolved_dest_dir.is_dir():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Configured ARCHIVE_DIR is not a directory: {resolved_dest_dir}",
            )
        return resolved_dest_dir

    def validate_video_and_clips(
        self,
        video: Video,
        allowed_roots: list[str] | None = None,
        custom_archive_dir: Path | None = None,
    ) -> tuple[Path, Path]:
        """Validate video status, clip segments, source file, and destination root.

        Returns:
            tuple[Path, Path]: (resolved_source_path, resolved_archive_dir)
        """
        if video.status == VideoStatus.REPLACED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video with id {video.id} is already replaced",
            )
        if video.status == VideoStatus.DISCARDED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video with id {video.id} is discarded and cannot be processed",
            )

        if not video.clips:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video with id {video.id} has no clip segments to process",
            )

        # Validate clip boundaries
        for clip in video.clips:
            if clip.start_seconds < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid clip segment start_seconds: {clip.start_seconds}",
                )
            if clip.end_seconds <= clip.start_seconds:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Clip segment end_seconds ({clip.end_seconds}) must be greater "
                        f"than start_seconds ({clip.start_seconds})"
                    ),
                )
            if video.duration is not None and clip.end_seconds > video.duration:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Clip segment end_seconds ({clip.end_seconds}) exceeds video "
                        f"duration ({video.duration})"
                    ),
                )

        resolved_source = self.validate_source_file(Path(video.path), allowed_roots=allowed_roots)
        resolved_archive = self.validate_destination_root(custom_archive_dir=custom_archive_dir)

        return resolved_source, resolved_archive

    def check_active_job(self, db: Session, video_id: int) -> None:
        """Reject duplicate active jobs for the same video (idempotency protection)."""
        active_job = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.video_id == video_id,
                ProcessingJob.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
            )
            .first()
        )
        if active_job:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Active processing job #{active_job.id} already exists for video {video_id} "
                    f"(status: '{active_job.status}')"
                ),
            )

    def create_job(
        self,
        db: Session,
        video_id: int,
        force_reencode: bool = False,
        allowed_roots: list[str] | None = None,
        custom_archive_dir: Path | None = None,
    ) -> ProcessingJob:
        """Create a new queued processing job after validating video state and idempotency."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with id {video_id} not found",
            )

        # Idempotency check: reject if active job exists
        self.check_active_job(db=db, video_id=video_id)

        # Validate video, clips, and storage roots before enqueuing
        self.validate_video_and_clips(
            video=video,
            allowed_roots=allowed_roots,
            custom_archive_dir=custom_archive_dir,
        )

        job = ProcessingJob(
            video_id=video_id,
            status=JobStatus.QUEUED.value,
            progress=0.0,
            message="Processing job queued",
            strategy=None,
            job_metadata={
                "force_reencode": force_reencode,
                "clip_count": len(video.clips),
            },
            created_at=utc_now(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def run_job(
        self,
        job_id: int,
        db: Session | None = None,
        allowed_roots: list[str] | None = None,
        custom_archive_dir: Path | None = None,
    ) -> ProcessingJob:
        """Execute processing workflow for a persistent background job.

        Lifecycle:
        - Sets job status to RUNNING.
        - Renders clips to temporary output in the original video directory.
        - Validates temporary output is non-empty regular file.
        - Moves original video file to ARCHIVE_DIR with collision-safe name.
        - Atomically replaces original file path with rendered output.
        - Updates Video status to 'replaced' and job status to 'succeeded'.
        - On any failure, rolls back filesystem changes, preserves source & DB state,
          cleans temp output, and marks job as 'failed'.
        """
        own_session = db is None
        session: Session = SessionLocal() if own_session else db  # type: ignore[assignment]

        try:
            job = session.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if not job:
                logger.error("Processing job #%d not found", job_id)
                raise RuntimeError(f"Processing job #{job_id} not found")

            # Check if job was already cancelled or finished
            if job.status in (JobStatus.CANCELLED.value, JobStatus.SUCCEEDED.value):
                return job

            # Transition to RUNNING
            now = utc_now()
            job.status = JobStatus.RUNNING.value
            job.started_at = now
            job.progress = 0.1
            job.message = "Job running: validating inputs"
            job.updated_at = now
            session.commit()
            session.refresh(job)

            # Retrieve video
            video = session.query(Video).filter(Video.id == job.video_id).first()
            if not video:
                raise RuntimeError(f"Video #{job.video_id} not found for job #{job_id}")

            resolved_source, resolved_archive_dir = self.validate_video_and_clips(
                video=video,
                allowed_roots=allowed_roots,
                custom_archive_dir=custom_archive_dir,
            )

            # Generate unique temporary output file in the original video directory
            temp_filename = (
                f".processing_tmp_{resolved_source.stem}_"
                f"{uuid.uuid4().hex[:8]}{resolved_source.suffix}"
            )
            temp_output = resolved_source.parent / temp_filename
            job.temp_path = str(temp_output)
            job.progress = 0.2
            job.message = "Rendering clip segments with FFmpeg"
            job.updated_at = utc_now()
            session.commit()

            force_reencode = False
            if job.job_metadata and isinstance(job.job_metadata, dict):
                force_reencode = bool(job.job_metadata.get("force_reencode", False))

            archive_dest: Path | None = None

            try:
                # 1. Render segments using FFmpeg runner pipeline
                applied_strategy = render_segments_pipeline(
                    input_path=resolved_source,
                    segments=video.clips,
                    output_path=temp_output,
                    runner=self.runner,
                    builder=self.command_builder,
                    force_reencode=force_reencode,
                )

                job.strategy = applied_strategy
                job.progress = 0.7
                job.message = (
                    f"Render complete ({applied_strategy}); "
                    "validating output and archiving original"
                )
                job.updated_at = utc_now()
                session.commit()

                # 2. Validate rendered output is non-empty regular file
                if not temp_output.exists():
                    raise RuntimeError(f"Rendered temporary output does not exist: {temp_output}")
                if not temp_output.is_file():
                    raise RuntimeError(
                        f"Rendered temporary output is not a regular file: {temp_output}"
                    )
                if temp_output.stat().st_size == 0:
                    raise RuntimeError(
                        f"Rendered temporary output is empty (0 bytes): {temp_output}"
                    )

                # 3. Move original to ARCHIVE_DIR with collision-safe name
                archive_dest = get_collision_free_destination(
                    resolved_archive_dir, resolved_source.name
                )
                move_strategy = move_file_safely(resolved_source, archive_dest)

                job.archive_path = str(archive_dest)
                job.progress = 0.85
                job.message = "Original archived safely; performing atomic replacement"
                job.updated_at = utc_now()
                session.commit()

                # 4. Atomically replace original path with rendered file
                try:
                    os.replace(temp_output, resolved_source)
                except Exception as replace_err:
                    # Rollback: restore original from archive back to source
                    logger.error(
                        "Failed to replace original file with temp output: %s",
                        replace_err,
                    )
                    if archive_dest.exists() and not resolved_source.exists():
                        try:
                            move_file_safely(archive_dest, resolved_source)
                        except Exception as restore_err:
                            logger.critical(
                                "Failed to restore original file from archive: %s",
                                restore_err,
                            )
                    raise RuntimeError(
                        f"Atomic replacement of original path failed: {replace_err}"
                    ) from replace_err

                # 5. Database updates: set Video.status to replaced only after filesystem
                # steps succeed
                try:
                    now_done = utc_now()
                    video.status = VideoStatus.REPLACED.value
                    video.size = resolved_source.stat().st_size
                    video.original_path = video.original_path or str(resolved_source)
                    video.move_metadata = {
                        "archived_to": str(archive_dest),
                        "render_strategy": applied_strategy,
                        "archive_strategy": move_strategy,
                        "processed_at": now_done.isoformat(),
                    }
                    video.updated_at = now_done

                    job.status = JobStatus.SUCCEEDED.value
                    job.progress = 1.0
                    job.message = "Video clips successfully rendered, archived, and replaced"
                    job.output_path = str(resolved_source)
                    job.archive_path = str(archive_dest)
                    job.completed_at = now_done
                    job.updated_at = now_done
                    session.commit()
                    session.refresh(video)
                    session.refresh(job)
                    return job

                except Exception as db_err:
                    session.rollback()
                    logger.error("Database update failed after file replacement: %s", db_err)
                    # Rollback filesystem: restore original from archive
                    try:
                        if resolved_source.exists():
                            resolved_source.unlink(missing_ok=True)
                        if archive_dest.exists():
                            move_file_safely(archive_dest, resolved_source)
                    except Exception as rollback_fs_err:
                        logger.critical(
                            "Failed to restore original after DB error: %s",
                            rollback_fs_err,
                        )
                    raise RuntimeError(
                        f"Database commit failed after replacement; source restored: {db_err}"
                    ) from db_err

            except Exception as pipeline_err:
                logger.error("Processing pipeline failed for job #%d: %s", job_id, pipeline_err)
                # Cleanup temp output if still around
                try:
                    if temp_output.exists():
                        temp_output.unlink(missing_ok=True)
                except Exception:
                    pass

                # If original was moved to archive but replacement wasn't finished, restore original
                if archive_dest and archive_dest.exists() and not resolved_source.exists():
                    try:
                        move_file_safely(archive_dest, resolved_source)
                    except Exception as restore_err:
                        logger.critical(
                            "Failed to restore original during cleanup: %s",
                            restore_err,
                        )

                # Record failed job state
                try:
                    fail_now = utc_now()
                    job.status = JobStatus.FAILED.value
                    job.error = str(pipeline_err)
                    job.message = f"Processing failed: {pipeline_err}"
                    job.completed_at = fail_now
                    job.updated_at = fail_now
                    session.commit()
                    session.refresh(job)
                except Exception:
                    session.rollback()

                raise

        finally:
            if own_session:
                session.close()

    def cancel_job(self, db: Session, job_id: int) -> ProcessingJob:
        """Cancel a pending or running processing job."""
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Processing job with id {job_id} not found",
            )

        if job.status in (
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job #{job_id} is already '{job.status}' and cannot be cancelled",
            )

        now = utc_now()
        job.status = JobStatus.CANCELLED.value
        job.message = "Job cancelled by request"
        job.completed_at = now
        job.updated_at = now
        db.commit()
        db.refresh(job)
        return job

    def get_job(self, db: Session, job_id: int) -> ProcessingJob:
        """Fetch processing job by ID or raise 404."""
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Processing job with id {job_id} not found",
            )
        return job

    def list_jobs_for_video(self, db: Session, video_id: int) -> list[ProcessingJob]:
        """List all processing jobs for a video ordered newest first."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with id {video_id} not found",
            )
        return (
            db.query(ProcessingJob)
            .filter(ProcessingJob.video_id == video_id)
            .order_by(ProcessingJob.id.desc())
            .all()
        )

    def get_latest_job_for_video(self, db: Session, video_id: int) -> ProcessingJob | None:
        """Fetch the most recent processing job for a video if one exists."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with id {video_id} not found",
            )
        return (
            db.query(ProcessingJob)
            .filter(ProcessingJob.video_id == video_id)
            .order_by(ProcessingJob.id.desc())
            .first()
        )


processing_service = ProcessingService()
