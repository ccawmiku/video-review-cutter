"""FFmpeg Service Placeholder Module.

Provides service interface placeholders for video inspection, thumbnail generation,
and clipping operations. Concrete processing logic will be implemented in subsequent issues.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import settings


class FFmpegService:
    """Service wrapper for interacting with ffmpeg and ffprobe binaries."""

    def __init__(
        self,
        ffmpeg_path: str | None = None,
        ffprobe_path: str | None = None,
    ) -> None:
        self.ffmpeg_path = ffmpeg_path or settings.ffmpeg_path
        self.ffprobe_path = ffprobe_path or settings.ffprobe_path

    def is_available(self) -> bool:
        """Check if FFmpeg executable is present in PATH or configured location."""
        return shutil.which(self.ffmpeg_path) is not None

    def get_version(self) -> str | None:
        """Retrieve FFmpeg version string if binary exists."""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0:
                first_line = result.stdout.splitlines()[0] if result.stdout else ""
                return first_line.strip()
        except Exception:
            pass
        return None

    def probe_video(self, video_path: Path) -> dict[str, Any]:
        """Placeholder for probing video metadata (duration, codecs, resolution).

        Note: Video scanning and metadata extraction will be implemented in a dedicated issue.
        """
        raise NotImplementedError("Video probing is not implemented in Issue #1 scaffold.")

    def generate_thumbnail(
        self,
        video_path: Path,
        output_path: Path,
        time_offset: float = 1.0,
    ) -> Path:
        """Placeholder for extracting thumbnail frame from video.

        Note: Thumbnail generation will be implemented in a dedicated issue.
        """
        raise NotImplementedError("Thumbnail generation is not implemented in Issue #1 scaffold.")

    def trim_video(
        self,
        input_path: Path,
        output_path: Path,
        start_seconds: float,
        end_seconds: float,
    ) -> Path:
        """Placeholder for trimming video clip between timestamps.

        Note: Video clipping and export will be implemented in a dedicated issue.
        """
        raise NotImplementedError("Video trimming is not implemented in Issue #1 scaffold.")


ffmpeg_service = FFmpegService()
