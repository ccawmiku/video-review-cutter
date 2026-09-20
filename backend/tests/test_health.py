"""Test health endpoint and placeholder components."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.ffmpeg import FFmpegService

client = TestClient(app)


def test_root_endpoint() -> None:
    """Ensure root metadata endpoint returns 200 and links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert data["service"] == "Video Review & Cutter Backend API"
    assert data["health"] == "/health"


def test_health_endpoint() -> None:
    """Ensure root /health endpoint responds with expected status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "video-review-cutter-backend"
    assert "database" in data
    assert "ffmpeg" in data
    assert "storage" in data


def test_api_health_endpoint() -> None:
    """Ensure /api/health endpoint responds identically."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"]["type"] == "sqlite"


def test_ffmpeg_service_placeholders() -> None:
    """Ensure FFmpeg placeholder raises NotImplementedError for unimplemented methods."""
    svc = FFmpegService(ffmpeg_path="nonexistent-ffmpeg", ffprobe_path="nonexistent-ffprobe")
    assert svc.is_available() is False
    assert svc.get_version() is None

    test_path = Path("dummy.mp4")
    with pytest.raises(FileNotFoundError):
        svc.probe_video(test_path)

    with pytest.raises(NotImplementedError):
        svc.generate_thumbnail(test_path, Path("out.jpg"))

    with pytest.raises(NotImplementedError):
        svc.trim_video(test_path, Path("trimmed.mp4"), 0.0, 10.0)
