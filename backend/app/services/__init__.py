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
from app.services.ffmpeg_runner import (
    FFmpegCommandBuilder,
    FFmpegRunner,
    MockFFmpegRunner,
    SubprocessFFmpegRunner,
    render_segments_pipeline,
)
from app.services.processing import ProcessingService, processing_service
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
    "FFmpegCommandBuilder",
    "FFmpegRunner",
    "FFmpegService",
    "MockFFmpegRunner",
    "ProcessingService",
    "RangeNotSatisfiableError",
    "StreamingService",
    "SubprocessFFmpegRunner",
    "VideoProbeInterface",
    "catalog_service",
    "clip_service",
    "discard_service",
    "ffmpeg_service",
    "guess_video_mime_type",
    "move_file_safely",
    "parse_probe_output",
    "parse_range_header",
    "processing_service",
    "render_segments_pipeline",
    "streaming_service",
    "validate_video_path",
]
