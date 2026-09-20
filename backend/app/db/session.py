"""Database connection and session management module.

Provides SQLite engine and session factory placeholders for future data models.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


def _ensure_sqlite_directory() -> None:
    """Ensure directory for SQLite database file exists before connecting."""
    if "sqlite:///" in settings.database_url:
        db_raw = settings.database_url.replace("sqlite:///", "")
        db_path = Path(db_raw)
        if db_path.parent and not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)


# Ensure DB directory exists
_ensure_sqlite_directory()

# Engine setup for SQLite
# check_same_thread=False allows multi-threaded access common in web servers
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to retrieve database session."""
    _ensure_sqlite_directory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> bool:
    """Validate database connectivity for health check."""
    try:
        _ensure_sqlite_directory()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def init_db() -> None:
    """Initialize database tables safely on application startup."""
    _ensure_sqlite_directory()
    # Import models here so Base.metadata is aware of all declared entities
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
