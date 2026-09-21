"""Video catalog ORM models module.

Defines SQLite schema for indexed video records and status tracking.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, BigInteger, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.clip import ClipSegment
    from app.models.job import ProcessingJob


def utc_now() -> datetime:
    """Return timezone-aware current UTC timestamp."""
    return datetime.now(UTC)


class VideoStatus(enum.StrEnum):
    """Workflow status values for catalog video records."""

    UNPROCESSED = "unprocessed"
    NO_ACTION = "no_action"
    CLIP_SELECTED = "clip_selected"
    REPLACED = "replaced"
    DISCARDED = "discarded"


class Video(Base):
    """SQLAlchemy model representing a discovered video file in configured storage."""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String(1024), unique=True, index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default=VideoStatus.UNPROCESSED.value,
        nullable=False,
        index=True,
    )
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    bit_rate: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    scan_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    scan_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Auditable move metadata for discard / lifecycle workflow
    original_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    move_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    last_scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    clips: Mapped[list[ClipSegment]] = relationship(
        "ClipSegment",
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="[ClipSegment.order_index, ClipSegment.start_seconds, ClipSegment.id]",
    )

    jobs: Mapped[list[ProcessingJob]] = relationship(
        "ProcessingJob",
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="ProcessingJob.id.desc()",
    )

    @property
    def current_path(self) -> str:
        """Auditable current path of the video file on disk."""
        return self.path
