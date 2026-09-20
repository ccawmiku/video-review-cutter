"""Services package containing core domain service interfaces and implementations."""

from app.services.catalog import CatalogService, catalog_service
from app.services.clip import ClipService, clip_service
from app.services.discard import DiscardService, discard_service, move_file_safely
from app.services.ffmpeg import (
    FFmpegService,
    VideoProbeInterface,
    ffmpeg_service,
    parse_probe_output,
)
from app.services.streaming import (
    RangeNotSatisfiableError,
    StreamingService,
    guess_video_mime_type,
    parse_range_header,
    streaming_service,
    validate_video_path,
)

__all__ = [
    "CatalogService",
    "ClipService",
    "DiscardService",
    "FFmpegService",
    "RangeNotSatisfiableError",
    "StreamingService",
    "VideoProbeInterface",
    "catalog_service",
    "clip_service",
    "discard_service",
    "ffmpeg_service",
    "guess_video_mime_type",
    "move_file_safely",
    "parse_probe_output",
    "parse_range_header",
    "streaming_service",
    "validate_video_path",
]
