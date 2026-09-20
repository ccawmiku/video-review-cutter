"""Tests for video database models and schema initialization."""

import tempfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base
from app.models.video import Video, VideoStatus


@pytest.fixture
def temp_db_session() -> Generator[Session, None, None]:
    """Create a temporary SQLite database session for model testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test.db"
        engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(bind=engine)
        SessionTest = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionTest()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()


def test_video_model_creation_and_defaults(temp_db_session: Session) -> None:
    """Ensure Video model sets expected default values on insertion."""
    video = Video(
        path="/media/videos/test1.mp4",
        filename="test1.mp4",
        size=1024 * 1024 * 50,
        duration=120.5,
    )
    temp_db_session.add(video)
    temp_db_session.commit()

    saved = temp_db_session.query(Video).filter(Video.path == "/media/videos/test1.mp4").first()
    assert saved is not None
    assert saved.id is not None
    assert saved.status == VideoStatus.UNPROCESSED.value
    assert saved.duration == 120.5
    assert saved.size == 52428800
    assert saved.filename == "test1.mp4"
    assert isinstance(saved.created_at, datetime)
    assert isinstance(saved.updated_at, datetime)
    assert isinstance(saved.last_scanned_at, datetime)


def test_video_status_enum_values() -> None:
    """Validate that VideoStatus defines all expected lifecycle states."""
    expected = {"unprocessed", "no_action", "clip_selected", "replaced", "discarded"}
    actual = {s.value for s in VideoStatus}
    assert actual == expected


def test_video_path_unique_constraint(temp_db_session: Session) -> None:
    """Ensure duplicate video paths trigger SQLite unique constraint violation."""
    v1 = Video(
        path="/media/videos/duplicate.mp4",
        filename="duplicate.mp4",
        size=1000,
    )
    temp_db_session.add(v1)
    temp_db_session.commit()

    v2 = Video(
        path="/media/videos/duplicate.mp4",
        filename="duplicate2.mp4",
        size=2000,
    )
    temp_db_session.add(v2)
    with pytest.raises(IntegrityError):
        temp_db_session.commit()
