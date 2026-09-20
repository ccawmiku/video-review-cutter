"""Video catalog ORM models module.

Defines SQLite schema for indexed video records and status tracking.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


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
