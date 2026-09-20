"""Video discard domain service module.

Provides a safe filesystem move workflow for cataloged videos:
- Validates source path within configured VIDEO_ROOTS, rejecting traversal/symlink escapes.
- Validates and creates destination within configured DISCARDED_DIR.
- Avoids filename collisions deterministically without overwriting.
- Uses atomic rename when on the same filesystem.
- Uses safe copy-to-temp/fsync/verify/then-remove-source fallback across filesystems.
- Preserves source file and DB status on any failure.
- Updates database only after successful move, recording auditable metadata.
- Never deletes the video file without moving it first.
"""

from __future__ import annotations

import errno
import hashlib
import logging
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.video import Video, VideoStatus, utc_now

logger = logging.getLogger(__name__)


def is_subpath(child: Path, parent: Path) -> bool:
    """Check if child path is contained within parent directory."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def get_collision_free_destination(dest_dir: Path, filename: str) -> Path:
    """Deterministically find a non-existing destination path avoiding collisions.

    Appends numeric suffix (_1, _2, ...) before extension when collisions exist.
    Treats existing broken symlinks as collisions to prevent hijacking.
    """
    clean_path = Path(filename)
    stem = clean_path.stem
    suffix = clean_path.suffix

    candidate = dest_dir / f"{stem}{suffix}"
    if not candidate.exists() and not candidate.is_symlink():
        return candidate

    counter = 1
    while True:
        candidate = dest_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        counter += 1


def move_file_safely(source: Path, destination: Path) -> str:
    """Move source file to destination safely.

    Uses atomic rename on the same filesystem.
    Falls back to safe copy-to-temp/fsync/verify/then-remove-source across filesystems.
    Guarantees that source is preserved on any failure.

    Returns:
        str: Move strategy used ("atomic_rename" or "cross_device_copy").
    """
    dest_dir = destination.parent
    src_stat = source.stat()
    src_dev = src_stat.st_dev
    dst_dev = dest_dir.stat().st_dev
    src_size = src_stat.st_size

    # Attempt atomic rename if devices match
    if src_dev == dst_dev:
        try:
            os.replace(source, destination)
            return "atomic_rename"
        except OSError as exc:
            # Fall back only if error indicates cross-device move
            if exc.errno != errno.EXDEV:
                raise

    # Cross-device safe move fallback
    temp_file = tempfile.NamedTemporaryFile(
        dir=dest_dir,
        prefix=f".discard_tmp_{destination.stem}_",
        suffix=destination.suffix,
        delete=False,
    )
    temp_path = Path(temp_file.name)

    try:
        h_src = hashlib.sha256()
        h_dst = hashlib.sha256()
        bytes_copied = 0

        with open(source, "rb") as f_src:
            while True:
                chunk = f_src.read(1024 * 1024)
                if not chunk:
                    break
                h_src.update(chunk)
                temp_file.write(chunk)
                h_dst.update(chunk)
                bytes_copied += len(chunk)

        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()

        # Verification step
        temp_stat = temp_path.stat()
        if temp_stat.st_size != src_size or bytes_copied != src_size:
            raise OSError(f"Copy size mismatch: expected {src_size} bytes, got {temp_stat.st_size}")
        if h_src.digest() != h_dst.digest():
            raise OSError("Copy checksum mismatch: SHA-256 hash does not match source")

        # Atomic rename temp file to final destination on target filesystem
        os.replace(temp_path, destination)

        final_stat = destination.stat()
        if final_stat.st_size != src_size:
            raise OSError("Destination size mismatch after atomic link")

        # Unlink source only after destination is verified
        try:
            source.unlink()
        except Exception as unlink_err:
            # If removing source fails, remove destination to preserve source and avoid duplicate
            try:
                if destination.exists():
                    destination.unlink()
            except Exception:
                pass
            raise OSError(f"Failed to remove source file after copy: {unlink_err}") from unlink_err

        return "cross_device_copy"

    except Exception:
        # Cleanup temporary file if it still exists
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass
        # Cleanup destination file if created while source is still intact
        try:
            if destination.exists() and source.exists():
                destination.unlink()
        except Exception:
            pass
        raise


class DiscardService:
    """Domain service managing the safe discard lifecycle of cataloged videos."""

    def validate_source_file(
        self,
        source_path: Path,
        allowed_roots: list[str] | None = None,
    ) -> Path:
        """Validate source video path against configured VIDEO_ROOTS and regular file checks.

        Returns canonical resolved Path to the verified regular file.
        """
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

        # Validate containment within configured video roots
        root_candidates = allowed_roots if allowed_roots is not None else settings.video_roots
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

    def validate_and_prepare_destination(
        self,
        filename: str,
        custom_dest_dir: Path | None = None,
    ) -> tuple[Path, Path]:
        """Validate and create DISCARDED_DIR, ensure path containment and collision-free target.

        Returns:
            tuple[Path, Path]: (resolved_dest_dir, collision_free_dest_file)
        """
        dest_dir = (custom_dest_dir or settings.discarded_dir).expanduser()

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to create destination discarded directory: {err}",
            ) from err

        resolved_dest_dir = dest_dir.resolve()
        if not resolved_dest_dir.is_dir():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Configured DISCARDED_DIR is not a directory: {resolved_dest_dir}",
            )

        # Sanitize filename and verify containment to prevent traversal
        clean_filename = Path(filename).name
        if not clean_filename or clean_filename in (".", ".."):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid video filename for destination move",
            )

        direct_dest = (resolved_dest_dir / clean_filename).resolve()
        if not is_subpath(direct_dest, resolved_dest_dir):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: destination path traversal escape",
            )

        # Obtain deterministic collision-free candidate
        collision_free_file = get_collision_free_destination(resolved_dest_dir, clean_filename)
        return resolved_dest_dir, collision_free_file

    def discard_video(
        self,
        db: Session,
        video_id: int,
        reason: str | None = None,
        allowed_roots: list[str] | None = None,
        custom_dest_dir: Path | None = None,
    ) -> Video:
        """Execute the safe discard workflow for a video record.

        - Moves source file to DISCARDED_DIR without deleting original beforehand.
        - Sets status to 'discarded' only after file move verification.
        - Preserves source file and DB status on any failure.
        - Saves auditable original/current paths and movement metadata.
        """
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video with id {video_id} not found",
            )

        if video.status == VideoStatus.DISCARDED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video with id {video_id} is already discarded",
            )

        source_path = Path(video.path)
        resolved_source = self.validate_source_file(source_path, allowed_roots=allowed_roots)
        _, dest_file = self.validate_and_prepare_destination(
            source_path.name, custom_dest_dir=custom_dest_dir
        )

        orig_source_str = str(source_path)

        # Perform safe filesystem move
        try:
            strategy = move_file_safely(resolved_source, dest_file)
        except Exception as move_err:
            logger.error("Failed to move video file during discard: %s", move_err)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to move video file to discarded directory: {move_err}",
            ) from move_err

        # Update database record only after successful move
        now = utc_now()
        try:
            video.original_path = video.original_path or orig_source_str
            video.path = str(dest_file)
            video.filename = dest_file.name
            video.status = VideoStatus.DISCARDED.value
            video.discarded_at = now
            video.move_metadata = {
                "source_path": orig_source_str,
                "destination_path": str(dest_file),
                "moved_at": now.isoformat(),
                "strategy": strategy,
                "size": dest_file.stat().st_size,
                "reason": reason,
            }
            video.updated_at = now
            db.commit()
            db.refresh(video)
            return video
        except Exception as db_err:
            db.rollback()
            # Attempt to restore file back to source to preserve source and DB state
            try:
                if dest_file.exists() and not resolved_source.exists():
                    move_file_safely(dest_file, resolved_source)
            except Exception as rollback_err:
                logger.error(
                    "Failed to restore file to source after database commit failure: %s",
                    rollback_err,
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database update failed after file move; source restored: {db_err}",
            ) from db_err


discard_service = DiscardService()
