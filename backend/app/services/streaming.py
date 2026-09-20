"""Video preview streaming service module.

Provides secure HTTP Range chunked streaming for video preview playback,
supporting full 200, partial 206, and unsatisfiable 416 responses,
without buffering the whole file in memory.
Enforces path safety checks against configured VIDEO_ROOTS, preventing
configured-root escapes and symlink traversal escapes.
"""

from __future__ import annotations

import email.utils
import logging
import mimetypes
from collections.abc import AsyncGenerator
from pathlib import Path

import anyio
from fastapi import HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.models.video import Video

logger = logging.getLogger(__name__)

# Standard fallback MIME types for video extensions
DEFAULT_MIME_TYPES: dict[str, str] = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
    ".m4v": "video/mp4",
    ".ts": "video/mp2t",
    ".ogv": "video/ogg",
    ".3gp": "video/3gpp",
}


class RangeNotSatisfiableError(Exception):
    """Exception raised when an HTTP Range request cannot be satisfied."""

    def __init__(self, file_size: int, message: str = "Requested range not satisfiable") -> None:
        super().__init__(message)
        self.file_size = file_size


def guess_video_mime_type(path: Path) -> str:
    """Determine MIME type from file extension with fallback."""
    suffix = path.suffix.lower()
    if suffix in DEFAULT_MIME_TYPES:
        return DEFAULT_MIME_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def parse_range_header(range_header: str | None, file_size: int) -> tuple[int, int] | None:
    """Parse single HTTP Range header in bytes unit.

    Returns:
        tuple[int, int]: (start, end) byte indices (inclusive).
        None: When Range header is omitted or empty (full representation requested).

    Raises:
        RangeNotSatisfiableError: If range format is invalid, multiple ranges are requested,
            or the requested range is outside available byte bounds.
    """
    if not range_header or not range_header.strip():
        return None

    header = range_header.strip()
    if not header.lower().startswith("bytes="):
        raise RangeNotSatisfiableError(file_size, "Only bytes range unit supported")

    range_spec = header[6:].strip()
    if "," in range_spec or not range_spec:
        raise RangeNotSatisfiableError(file_size, "Multi-range or empty range not supported")

    if "-" not in range_spec:
        raise RangeNotSatisfiableError(file_size, "Malformed byte range specification")

    parts = range_spec.split("-", 1)
    start_str, end_str = parts[0].strip(), parts[1].strip()

    if file_size <= 0:
        raise RangeNotSatisfiableError(0, "File is empty; range not satisfiable")

    if start_str and end_str:
        try:
            start = int(start_str)
            end = int(end_str)
        except ValueError:
            raise RangeNotSatisfiableError(file_size, "Non-integer byte range") from None
        if start < 0 or start > end or start >= file_size:
            raise RangeNotSatisfiableError(file_size, "Invalid byte range offsets")
        return (start, min(end, file_size - 1))

    elif start_str and not end_str:
        try:
            start = int(start_str)
        except ValueError:
            raise RangeNotSatisfiableError(file_size, "Non-integer byte range") from None
        if start < 0 or start >= file_size:
            raise RangeNotSatisfiableError(file_size, "Start byte offset beyond EOF")
        return (start, file_size - 1)

    elif not start_str and end_str:
        try:
            suffix = int(end_str)
        except ValueError:
            raise RangeNotSatisfiableError(file_size, "Non-integer suffix length") from None
        if suffix <= 0:
            raise RangeNotSatisfiableError(file_size, "Suffix byte length must be positive")
        if suffix >= file_size:
            return (0, file_size - 1)
        return (file_size - suffix, file_size - 1)

    else:
        raise RangeNotSatisfiableError(file_size, "Missing both start and end in range")


def is_subpath(child: Path, parent: Path) -> bool:
    """Check if child path is contained within parent directory."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_video_path(
    path_str: str | None,
    allowed_roots: list[str] | None = None,
) -> Path:
    """Validate video file path against configured video roots and security constraints.

    Rejects missing files, non-regular files (directories, sockets), paths escaping
    configured video roots, and symlinks escaping configured video roots.

    Returns:
        Path: Canonical resolved Path to the verified regular file.

    Raises:
        HTTPException 404: If file is missing or not a regular file.
        HTTPException 403: If path or symlink escapes configured video roots.
    """
    if not path_str or not path_str.strip():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video record has no path configured",
        )

    target_path = Path(path_str.strip())

    # Resolve and validate configured roots
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
        logger.error("No valid configured video roots found during preview request")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: no valid configured video roots available",
        )

    # Check existence
    if not target_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video file not found: {target_path.name}",
        )

    # Check that it is a regular file
    if not target_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video path is not a regular file",
        )

    # Resolve real canonical path
    try:
        resolved_path = target_path.resolve(strict=True)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unable to resolve video path: {err}",
        ) from err

    if not resolved_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resolved video path is not a regular file",
        )

    # Verify containment within configured roots
    raw_in_root = any(is_subpath(target_path.absolute(), root) for root in valid_roots)
    resolved_in_root = any(is_subpath(resolved_path, root) for root in valid_roots)

    # Check symlink escape
    if target_path.is_symlink() and not resolved_in_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: symlink escape outside configured video roots",
        )

    if not resolved_in_root or not raw_in_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: video path outside configured video roots",
        )

    return resolved_path


class StreamingService:
    """Service providing secure chunked video preview streaming with HTTP Range support."""

    def __init__(self, chunk_size: int = 64 * 1024) -> None:
        self.chunk_size = chunk_size

    async def stream_file_chunks(
        self,
        file_path: Path,
        start: int,
        end: int,
    ) -> AsyncGenerator[bytes, None]:
        """Stream byte range asynchronously without whole-file buffering."""
        remaining = end - start + 1
        async with await anyio.open_file(file_path, mode="rb") as f:
            if start > 0:
                await f.seek(start)
            while remaining > 0:
                read_len = min(self.chunk_size, remaining)
                chunk = await f.read(read_len)
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    async def stream_video_preview(
        self,
        video: Video,
        request: Request,
        allowed_roots: list[str] | None = None,
    ) -> Response:
        """Process preview request, validating paths and serving full 200 or partial 206/416."""
        resolved_path = validate_video_path(video.path, allowed_roots=allowed_roots)

        try:
            file_stat = resolved_path.stat()
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Failed to stat video file: {exc}",
            ) from None

        file_size = file_stat.st_size
        mime_type = guess_video_mime_type(resolved_path)
        last_modified = email.utils.formatdate(file_stat.st_mtime, usegmt=True)
        etag = f'"{int(file_stat.st_mtime)}-{file_size}"'

        range_header = request.headers.get("range")
        try:
            byte_range = parse_range_header(range_header, file_size)
        except RangeNotSatisfiableError:
            return Response(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={
                    "Accept-Ranges": "bytes",
                    "Content-Range": f"bytes */{file_size}",
                    "Content-Length": "0",
                },
            )

        # Full 200 response
        if byte_range is None:
            headers = {
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Last-Modified": last_modified,
                "ETag": etag,
            }
            if request.method == "HEAD" or file_size == 0:
                return Response(
                    content=b"",
                    status_code=status.HTTP_200_OK,
                    media_type=mime_type,
                    headers=headers,
                )
            return StreamingResponse(
                self.stream_file_chunks(resolved_path, 0, file_size - 1),
                status_code=status.HTTP_200_OK,
                media_type=mime_type,
                headers=headers,
            )

        # Partial 206 response
        start, end = byte_range
        content_length = end - start + 1
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
            "Last-Modified": last_modified,
            "ETag": etag,
        }
        if request.method == "HEAD":
            return Response(
                content=b"",
                status_code=status.HTTP_206_PARTIAL_CONTENT,
                media_type=mime_type,
                headers=headers,
            )

        return StreamingResponse(
            self.stream_file_chunks(resolved_path, start, end),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=mime_type,
            headers=headers,
        )


streaming_service = StreamingService()
