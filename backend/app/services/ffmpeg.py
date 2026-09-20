"""FFmpeg and FFprobe Service Module.

Provides injectable service interface for video inspection, metadata extraction,
thumbnail generation, and clipping operations.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.core.config import settings


@runtime_checkable
class VideoProbeInterface(Protocol):
    """Injectable interface for probing video files to extract metadata."""

    def probe_video(self, video_path: Path) -> dict[str, Any]:
        """Inspect video file and return probe metadata dictionary."""
        ...


def _parse_fps(rate_str: str | None) -> float | None:
    """Safely parse frame rate fraction (e.g. '30000/1001' or '25/1') to float."""
    if not rate_str or rate_str in ("0/0", "0"):
        return None
    try:
        if "/" in rate_str:
            parts = rate_str.split("/", 1)
            num = float(parts[0])
            den = float(parts[1])
            if den > 0:
                fps = round(num / den, 3)
                return fps if fps > 0 else None
        else:
            val = round(float(rate_str), 3)
            return val if val > 0 else None
    except (ValueError, ZeroDivisionError):
        return None
    return None


def _parse_int(val: Any) -> int | None:
    """Safely convert numeric string or number to integer."""
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _parse_duration(val: Any) -> float | None:
    """Safely parse duration string or number into positive float."""
    if val is None:
        return None
    try:
        dur = round(float(val), 3)
        return dur if dur >= 0 else None
    except (ValueError, TypeError):
        return None


def parse_probe_output(probe_data: dict[str, Any]) -> dict[str, Any]:
    """Extract standard metadata fields from raw ffprobe JSON output dictionary.

    Returns dict containing duration, width, height, codec, fps, bit_rate.
    Safely handles missing sections or non-numeric values.
    """
    if not isinstance(probe_data, dict):
        return {
            "duration": None,
            "width": None,
            "height": None,
            "codec": None,
            "fps": None,
            "bit_rate": None,
        }

    format_data = probe_data.get("format")
    if not isinstance(format_data, dict):
        format_data = {}

    streams = probe_data.get("streams")
    if not isinstance(streams, list):
        streams = []

    # Find primary video stream
    video_stream: dict[str, Any] = {}
    for stream in streams:
        if isinstance(stream, dict) and stream.get("codec_type") == "video":
            video_stream = stream
            break

    # Extract duration from format first, then fall back to video stream
    duration = _parse_duration(format_data.get("duration"))
    if duration is None and video_stream:
        duration = _parse_duration(video_stream.get("duration"))

    # Extract resolution and codec from video stream
    width = _parse_int(video_stream.get("width"))
    height = _parse_int(video_stream.get("height"))
    codec = video_stream.get("codec_name")
    if codec and not isinstance(codec, str):
        codec = str(codec)

    # Extract FPS
    fps = _parse_fps(video_stream.get("r_frame_rate"))
    if fps is None:
        fps = _parse_fps(video_stream.get("avg_frame_rate"))

    # Extract bit_rate
    bit_rate = _parse_int(format_data.get("bit_rate"))
    if bit_rate is None and video_stream:
        bit_rate = _parse_int(video_stream.get("bit_rate"))

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "codec": codec,
        "fps": fps,
        "bit_rate": bit_rate,
    }


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

    def is_probe_available(self) -> bool:
        """Check if FFprobe executable is present in PATH or configured location."""
        return shutil.which(self.ffprobe_path) is not None

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
        """Probe video metadata using ffprobe CLI.

        Returns raw JSON dictionary containing format and streams metadata.
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file does not exist: {video_path}")

        cmd = [
            self.ffprobe_path,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"ffprobe timed out probing {video_path}") from exc
        except Exception as exc:
            raise RuntimeError(f"ffprobe execution failed: {exc}") from exc

        if result.returncode != 0:
            err = result.stderr.strip() if result.stderr else f"exit code {result.returncode}"
            raise RuntimeError(f"ffprobe failed: {err}")

        try:
            return json.loads(result.stdout)  # type: ignore[no-any-return]
        except Exception as exc:
            raise ValueError(f"Invalid JSON returned by ffprobe: {exc}") from exc

    def generate_thumbnail(
        self,
        video_path: Path,
        output_path: Path,
        time_offset: float = 1.0,
    ) -> Path:
        """Placeholder for extracting thumbnail frame from video."""
        raise NotImplementedError("Thumbnail generation is not implemented in Issue #3.")

    def trim_video(
        self,
        input_path: Path,
        output_path: Path,
        start_seconds: float,
        end_seconds: float,
    ) -> Path:
        """Placeholder for trimming video clip between timestamps."""
        raise NotImplementedError("Video trimming is not implemented in Issue #3.")


ffmpeg_service = FFmpegService()
