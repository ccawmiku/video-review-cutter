"""Tests for FFmpeg service wrapper and probe metadata parsing."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.ffmpeg import FFmpegService, parse_probe_output


def test_parse_probe_output_complete() -> None:
    """Ensure complete ffprobe JSON output is parsed into structured metadata."""
    sample = {
        "format": {
            "duration": "145.678",
            "bit_rate": "2500000",
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        },
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "aac",
            },
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30000/1001",
            },
        ],
    }
    parsed = parse_probe_output(sample)
    assert parsed["duration"] == 145.678
    assert parsed["width"] == 1920
    assert parsed["height"] == 1080
    assert parsed["codec"] == "h264"
    assert parsed["fps"] == 29.97
    assert parsed["bit_rate"] == 2500000


def test_parse_probe_output_fallback_stream_duration() -> None:
    """Ensure parser falls back to video stream duration if format duration is absent."""
    sample = {
        "format": {},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
                "duration": "60.25",
                "avg_frame_rate": "24/1",
            }
        ],
    }
    parsed = parse_probe_output(sample)
    assert parsed["duration"] == 60.25
    assert parsed["width"] == 3840
    assert parsed["height"] == 2160
    assert parsed["codec"] == "hevc"
    assert parsed["fps"] == 24.0


def test_parse_probe_output_malformed_or_empty() -> None:
    """Ensure parser returns None for missing/invalid fields without crashing."""
    assert parse_probe_output({}) == {
        "duration": None,
        "width": None,
        "height": None,
        "codec": None,
        "fps": None,
        "bit_rate": None,
    }
    assert parse_probe_output("not-a-dict") == {  # type: ignore[arg-type]
        "duration": None,
        "width": None,
        "height": None,
        "codec": None,
        "fps": None,
        "bit_rate": None,
    }

    sample_invalid_numbers = {
        "format": {"duration": "invalid", "bit_rate": "bad"},
        "streams": [{"codec_type": "video", "r_frame_rate": "0/0", "width": "abc"}],
    }
    parsed = parse_probe_output(sample_invalid_numbers)
    assert parsed["duration"] is None
    assert parsed["width"] is None
    assert parsed["fps"] is None
    assert parsed["bit_rate"] is None


def test_ffmpeg_service_probe_video_missing_file() -> None:
    """Ensure probe_video raises FileNotFoundError when target file does not exist."""
    svc = FFmpegService()
    with pytest.raises(FileNotFoundError):
        svc.probe_video(Path("nonexistent_video.mp4"))


def test_ffmpeg_service_probe_video_mocked(tmp_path: Path) -> None:
    """Ensure probe_video invokes ffprobe subprocess and returns parsed dictionary."""
    dummy_file = tmp_path / "sample.mp4"
    dummy_file.write_bytes(b"dummy video data")

    svc = FFmpegService(ffprobe_path="mock-ffprobe")

    mock_output = {
        "format": {"duration": "42.0", "size": "1000"},
        "streams": [{"codec_type": "video", "codec_name": "h264"}],
    }

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(mock_output)

    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        res = svc.probe_video(dummy_file)
        assert res == mock_output
        mock_run.assert_called_once()


def test_ffmpeg_service_probe_video_error_handling(tmp_path: Path) -> None:
    """Ensure probe_video raises RuntimeError on nonzero returncode."""
    dummy_file = tmp_path / "bad.mp4"
    dummy_file.write_bytes(b"corrupt")

    svc = FFmpegService(ffprobe_path="mock-ffprobe")

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "Invalid data found when processing input"

    with patch("subprocess.run", return_value=mock_proc):
        with pytest.raises(RuntimeError) as exc_info:
            svc.probe_video(dummy_file)
        assert "Invalid data found" in str(exc_info.value)
