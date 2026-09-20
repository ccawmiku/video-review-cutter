"""Health check API endpoint module."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.db.session import check_db_connection
from app.services.ffmpeg import ffmpeg_service

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str
    app: str
    version: str
    environment: str
    database: dict[str, Any]
    ffmpeg: dict[str, Any]
    storage: dict[str, Any]


@router.get("/health", response_model=HealthResponse)
def get_health_status() -> HealthResponse:
    """Return backend service health and placeholder readiness."""
    db_connected = check_db_connection()
    ffmpeg_available = ffmpeg_service.is_available()

    return HealthResponse(
        status="ok",
        app="video-review-cutter-backend",
        version="0.1.0",
        environment=settings.environment,
        database={
            "status": "connected" if db_connected else "placeholder_ready",
            "type": "sqlite",
        },
        ffmpeg={
            "available": ffmpeg_available,
            "version": ffmpeg_service.get_version() if ffmpeg_available else None,
            "status": "placeholder_ready",
        },
        storage={
            "video_roots_count": len(settings.video_roots),
            "archive_configured": bool(str(settings.archive_dir)),
            "discarded_configured": bool(str(settings.discarded_dir)),
        },
    )
