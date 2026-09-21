"""Database connection and session management module.

Provides SQLite engine and session factory placeholders for future data models.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
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


def migrate_schema_compatibility(target_engine: Engine | None = None) -> None:
    """Ensure newly added columns exist in SQLite database if tables were pre-existing."""
    from sqlalchemy import inspect, text

    eng = target_engine or engine
    try:
        inspector = inspect(eng)
        table_names = inspector.get_table_names()
        if "videos" in table_names:
            columns = {col["name"] for col in inspector.get_columns("videos")}
            with eng.begin() as conn:
                if "original_path" not in columns:
                    conn.execute(text("ALTER TABLE videos ADD COLUMN original_path VARCHAR(1024)"))
                if "discarded_at" not in columns:
                    conn.execute(text("ALTER TABLE videos ADD COLUMN discarded_at DATETIME"))
                if "move_metadata" not in columns:
                    conn.execute(text("ALTER TABLE videos ADD COLUMN move_metadata JSON"))
        if "processing_jobs" not in table_names and "processing_jobs" in Base.metadata.tables:
            Base.metadata.tables["processing_jobs"].create(bind=eng, checkfirst=True)
    except Exception:
        pass


def init_db() -> None:
    """Initialize database tables safely on application startup."""
    _ensure_sqlite_directory()
    # Import models here so Base.metadata is aware of all declared entities
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_schema_compatibility(target_engine=engine)
