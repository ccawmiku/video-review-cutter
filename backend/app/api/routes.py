"""API router aggregator module."""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.videos import router as videos_router

api_router = APIRouter()

# Mount health endpoint under /api
api_router.include_router(health_router, prefix="", tags=["Health"])

# Mount video catalog endpoints under /api/videos and /api/catalog
api_router.include_router(videos_router, prefix="/videos", tags=["Videos"])
api_router.include_router(videos_router, prefix="/catalog", tags=["Catalog"])
