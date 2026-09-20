"""Main entrypoint for FastAPI backend application."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.routes import api_router
from app.core.config import settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
    # Initialize SQLite database schema placeholder on startup
    init_db()
    yield
    # Cleanup actions on shutdown (if any)


app = FastAPI(
    title="Video Review & Cutter Backend",
    description="Backend API service for video scanning, reviewing, and trimming workflow.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root() -> dict[str, str]:
    """Root metadata endpoint."""
    return {
        "service": "Video Review & Cutter Backend API",
        "docs": "/docs",
        "health": "/health",
        "api_health": "/api/health",
        "version": "0.1.0",
    }


# Include health router directly at root /health
app.include_router(health_router, prefix="", tags=["Health"])

# Include all API routes under /api
app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
    )
