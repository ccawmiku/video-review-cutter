"""Services package containing core domain service interfaces and implementations."""

from app.services.catalog import CatalogService, catalog_service
from app.services.clip import ClipService, clip_service
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
    "FFmpegService",
    "RangeNotSatisfiableError",
    "StreamingService",
    "VideoProbeInterface",
    "catalog_service",
    "clip_service",
    "ffmpeg_service",
    "guess_video_mime_type",
    "parse_probe_output",
    "parse_range_header",
    "streaming_service",
    "validate_video_path",
]
