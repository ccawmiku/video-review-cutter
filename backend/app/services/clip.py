"""Clip segment management and review decision domain service module."""

from __future__ import annotations

import logging
import math

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.clip import ClipSegment
from app.models.video import Video, VideoStatus, utc_now
from app.schemas.clip import ClipSegmentCreate, ClipSegmentUpdate
from app.schemas.decision import DecisionType

logger = logging.getLogger(__name__)


class ClipService:
    """Service handling clip segment CRUD and explicit review decisions."""

    def get_video_or_404(self, db: Session, video_id: int) -> Video:
        """Fetch video by primary key or raise 404 if not found."""
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with id {video_id} not found",
            )
        return video

    def list_clips(self, db: Session, video_id: int) -> list[ClipSegment]:
        """List clip segments for a video sorted by order_index, start_seconds, and id."""
        self.get_video_or_404(db=db, video_id=video_id)
        return (
            db.query(ClipSegment)
            .filter(ClipSegment.video_id == video_id)
            .order_by(
                ClipSegment.order_index.asc(),
                ClipSegment.start_seconds.asc(),
                ClipSegment.id.asc(),
            )
            .all()
        )

    def get_clip_or_404(self, db: Session, video_id: int, clip_id: int) -> ClipSegment:
        """Fetch clip segment belonging to video or raise 404."""
        self.get_video_or_404(db=db, video_id=video_id)
        clip = (
            db.query(ClipSegment)
            .filter(ClipSegment.id == clip_id, ClipSegment.video_id == video_id)
            .first()
        )
        if not clip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Clip segment with id {clip_id} not found for video {video_id}",
            )
        return clip

    def create_clip(
        self, db: Session, video_id: int, payload: ClipSegmentCreate
    ) -> ClipSegment:
        """Validate bounds against video duration and create clip segment."""
        video = self.get_video_or_404(db=db, video_id=video_id)

        # Validate duration boundary if known
        if video.duration is not None and payload.end_seconds > video.duration:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Segment end_seconds ({payload.end_seconds}) exceeds video duration "
                    f"({video.duration})"
                ),
            )

        order_idx = payload.order_index if payload.order_index is not None else 0

        clip = ClipSegment(
            video_id=video.id,
            start_seconds=payload.start_seconds,
            end_seconds=payload.end_seconds,
            label=payload.label,
            note=payload.note,
            order_index=order_idx,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(clip)
        db.commit()
        db.refresh(clip)
        return clip

    def update_clip(
        self,
        db: Session,
        video_id: int,
        clip_id: int,
        payload: ClipSegmentUpdate,
    ) -> ClipSegment:
        """Update existing clip segment with bound validations."""
        video = self.get_video_or_404(db=db, video_id=video_id)
        clip = self.get_clip_or_404(db=db, video_id=video_id, clip_id=clip_id)

        new_start = (
            payload.start_seconds if payload.start_seconds is not None else clip.start_seconds
        )
        new_end = payload.end_seconds if payload.end_seconds is not None else clip.end_seconds

        # Semantic validation
        if not math.isfinite(new_start) or new_start < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_seconds must be a finite non-negative number",
            )
        if not math.isfinite(new_end):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_seconds must be a finite number",
            )
        if new_end <= new_start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="end_seconds must be strictly greater than start_seconds",
            )
        if video.duration is not None and new_end > video.duration:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Segment end_seconds ({new_end}) exceeds video duration ({video.duration})"
                ),
            )

        clip.start_seconds = new_start
        clip.end_seconds = new_end
        if payload.label is not None:
            clip.label = payload.label
        if payload.note is not None:
            clip.note = payload.note
        if payload.order_index is not None:
            clip.order_index = payload.order_index

        clip.updated_at = utc_now()
        db.commit()
        db.refresh(clip)
        return clip

    def delete_clip(self, db: Session, video_id: int, clip_id: int) -> None:
        """Delete clip segment belonging to video."""
        clip = self.get_clip_or_404(db=db, video_id=video_id, clip_id=clip_id)
        db.delete(clip)
        db.commit()

    def record_decision(
        self, db: Session, video_id: int, decision: DecisionType
    ) -> Video:
        """Record explicit review decision: no_action or clip_selected.

        - no_action requires zero segments.
        - clip_selected requires at least one segment.
        Updates status and timestamps idempotently.
        """
        video = self.get_video_or_404(db=db, video_id=video_id)

        clip_count = (
            db.query(func.count(ClipSegment.id))
            .filter(ClipSegment.video_id == video_id)
            .scalar()
            or 0
        )

        if decision == DecisionType.NO_ACTION:
            if clip_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Cannot record decision 'no_action': video has {clip_count} "
                        "existing clip segment(s). Remove all segments first."
                    ),
                )
            target_status = VideoStatus.NO_ACTION.value
        elif decision == DecisionType.CLIP_SELECTED:
            if clip_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Cannot record decision 'clip_selected': video has 0 clip segments. "
                        "Add at least one clip segment first."
                    ),
                )
            target_status = VideoStatus.CLIP_SELECTED.value
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported decision '{decision}'",
            )

        video.status = target_status
        video.updated_at = utc_now()
        db.commit()
        db.refresh(video)
        return video


clip_service = ClipService()
