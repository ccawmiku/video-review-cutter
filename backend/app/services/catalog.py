"""Video catalog scanning and querying service module.

Handles recursive scanning of video root directories, metadata extraction via injectable
ffprobe service, database upserts, and filtered/sorted queries.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import desc, func, nulls_last
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.video import Video, VideoStatus, utc_now
from app.schemas.video import (
    ScanSummary,
    VideoListResponse,
    VideoRead,
)
from app.services.ffmpeg import (
    VideoProbeInterface,
    ffmpeg_service,
    parse_probe_output,
)

logger = logging.getLogger(__name__)

DEFAULT_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".flv",
    ".wmv",
    ".webm",
    ".m4v",
    ".ts",
}


class CatalogService:
    """Service managing video scanning, database synchronization, and catalog queries."""

    def __init__(
        self,
        probe_service: VideoProbeInterface | None = None,
        supported_extensions: set[str] | None = None,
    ) -> None:
        self.probe_service: VideoProbeInterface = (
            probe_service if probe_service is not None else ffmpeg_service
        )
        self.supported_extensions: set[str] = {
            ext.lower() for ext in (supported_extensions or DEFAULT_VIDEO_EXTENSIONS)
        }
        self.last_scan_summary: ScanSummary | None = None

    def scan(
        self,
        db: Session,
        roots: list[str] | None = None,
    ) -> ScanSummary:
        """Scan configured or specified video root directories recursively.

        Safely handles missing roots and malformed probe outputs without deleting existing rows.
        Upserts discovered video records and preserves previously assigned review statuses.
        """
        started_at = datetime.now(UTC)
        target_roots = roots if roots is not None else settings.video_roots

        missing_roots: list[str] = []
        scanned_roots: list[str] = []
        total_found = 0
        added = 0
        updated = 0
        failed = 0

        for raw_root in target_roots:
            root_path = Path(raw_root).expanduser()
            if not root_path.exists() or not root_path.is_dir():
                logger.warning(
                    "Video root directory '%s' does not exist or is not a directory; skipping.",
                    raw_root,
                )
                missing_roots.append(str(raw_root))
                continue

            scanned_roots.append(str(root_path.resolve()))

            # Recursively find video files
            for root_dir, _, filenames in os.walk(root_path):
                for filename in filenames:
                    file_ext = Path(filename).suffix.lower()
                    if file_ext not in self.supported_extensions:
                        continue

                    total_found += 1
                    file_path = Path(root_dir) / filename
                    resolved_path = str(file_path.resolve())

                    try:
                        file_stat = file_path.stat()
                        file_size = file_stat.st_size
                    except OSError as err:
                        logger.error("Failed to stat video file '%s': %s", resolved_path, err)
                        file_size = 0

                    # Probe video metadata using injectable probe service
                    probe_raw: dict[str, Any] | None = None
                    parsed_meta: dict[str, Any] = {}
                    scan_error: str | None = None

                    try:
                        probe_raw = self.probe_service.probe_video(file_path)
                        parsed_meta = parse_probe_output(probe_raw)
                    except Exception as exc:
                        scan_error = f"Probe error: {exc}"
                        failed += 1
                        logger.warning(
                            "Failed to probe video '%s': %s",
                            resolved_path,
                            scan_error,
                        )

                    # Check if video record already exists
                    existing_video = db.query(Video).filter(Video.path == resolved_path).first()

                    now = utc_now()
                    if existing_video:
                        existing_video.filename = filename
                        existing_video.size = file_size
                        existing_video.last_scanned_at = now

                        if scan_error is None:
                            existing_video.duration = parsed_meta.get("duration")
                            existing_video.width = parsed_meta.get("width")
                            existing_video.height = parsed_meta.get("height")
                            existing_video.codec = parsed_meta.get("codec")
                            existing_video.fps = parsed_meta.get("fps")
                            existing_video.bit_rate = parsed_meta.get("bit_rate")
                            existing_video.scan_metadata = probe_raw
                            existing_video.scan_error = None
                        else:
                            existing_video.scan_error = scan_error
                        # Status is intentionally preserved!
                        updated += 1
                    else:
                        new_video = Video(
                            path=resolved_path,
                            filename=filename,
                            size=file_size,
                            status=VideoStatus.UNPROCESSED.value,
                            duration=parsed_meta.get("duration") if scan_error is None else None,
                            width=parsed_meta.get("width") if scan_error is None else None,
                            height=parsed_meta.get("height") if scan_error is None else None,
                            codec=parsed_meta.get("codec") if scan_error is None else None,
                            fps=parsed_meta.get("fps") if scan_error is None else None,
                            bit_rate=parsed_meta.get("bit_rate") if scan_error is None else None,
                            scan_metadata=probe_raw if scan_error is None else None,
                            scan_error=scan_error,
                            created_at=now,
                            updated_at=now,
                            last_scanned_at=now,
                        )
                        db.add(new_video)
                        added += 1

        db.commit()

        finished_at = datetime.now(UTC)
        duration_seconds = round((finished_at - started_at).total_seconds(), 3)

        summary = ScanSummary(
            total_found=total_found,
            added=added,
            updated=updated,
            failed=failed,
            missing_roots=missing_roots,
            scanned_roots=scanned_roots,
            duration_seconds=duration_seconds,
            started_at=started_at,
            finished_at=finished_at,
        )

        self.last_scan_summary = summary
        return summary

    def list_videos(
        self,
        db: Session,
        status: VideoStatus | str | None = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "duration",
        order: str = "desc",
    ) -> VideoListResponse:
        """Query videos with status filtering, duration descending sorting, and pagination."""
        query = db.query(Video)

        # Status filter
        if status is not None:
            status_val = status.value if isinstance(status, VideoStatus) else str(status)
            query = query.filter(Video.status == status_val)

        # Sorting: defaults to duration descending with NULLs sorted last
        sort_desc = order.lower() == "desc"
        if sort_by == "duration":
            order_expr = (
                nulls_last(desc(Video.duration)) if sort_desc else nulls_last(Video.duration.asc())
            )
            query = query.order_by(order_expr, desc(Video.id))
        elif sort_by == "size":
            query = query.order_by(
                desc(Video.size) if sort_desc else Video.size.asc(), desc(Video.id)
            )
        elif sort_by == "created_at":
            query = query.order_by(
                desc(Video.created_at) if sort_desc else Video.created_at.asc(), desc(Video.id)
            )
        else:
            query = query.order_by(nulls_last(desc(Video.duration)), desc(Video.id))

        total = query.with_entities(func.count(Video.id)).scalar() or 0

        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        offset = (page - 1) * page_size

        records = query.offset(offset).limit(page_size).all()
        items = [VideoRead.model_validate(rec) for rec in records]
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return VideoListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def get_video_by_id(self, db: Session, video_id: int) -> Video | None:
        """Retrieve a single video record by database primary key."""
        return db.query(Video).filter(Video.id == video_id).first()


catalog_service = CatalogService()
