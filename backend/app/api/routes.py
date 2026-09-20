"""API router aggregator module."""

from fastapi import APIRouter

from app.api.health import router as health_router

api_router = APIRouter()

# Mount health endpoint under /api
api_router.include_router(health_router, prefix="", tags=["Health"])
