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
from app.models.clip import ClipSegment
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


def test_clip_segment_model_creation_and_ordering(temp_db_session: Session) -> None:
    """Ensure ClipSegment models link to Video, order properly, and have timestamps."""
    video = Video(
        path="/media/videos/clip_parent.mp4",
        filename="clip_parent.mp4",
        size=10000,
        duration=60.0,
    )
    temp_db_session.add(video)
    temp_db_session.commit()

    c1 = ClipSegment(
        video_id=video.id,
        start_seconds=10.0,
        end_seconds=20.0,
        label="Highlight 1",
        note="Good action",
        order_index=1,
    )
    c2 = ClipSegment(
        video_id=video.id,
        start_seconds=0.0,
        end_seconds=5.5,
        label="Intro",
        note=None,
        order_index=0,
    )
    temp_db_session.add_all([c1, c2])
    temp_db_session.commit()

    # Query video and inspect relationship ordering
    temp_db_session.expire_all()
    saved_video = temp_db_session.query(Video).filter(Video.id == video.id).first()
    assert saved_video is not None
    assert len(saved_video.clips) == 2
    # clips should be ordered by order_index: c2 (order_index=0) before c1 (order_index=1)
    assert saved_video.clips[0].order_index == 0
    assert saved_video.clips[0].label == "Intro"
    assert saved_video.clips[0].start_seconds == 0.0
    assert saved_video.clips[0].end_seconds == 5.5
    assert isinstance(saved_video.clips[0].created_at, datetime)
    assert isinstance(saved_video.clips[0].updated_at, datetime)

    assert saved_video.clips[1].order_index == 1
    assert saved_video.clips[1].label == "Highlight 1"
    assert saved_video.clips[1].note == "Good action"


def test_clip_segment_cascade_deletion(temp_db_session: Session) -> None:
    """Ensure deleting a Video cascades and deletes all associated ClipSegments."""
    video = Video(
        path="/media/videos/to_delete.mp4",
        filename="to_delete.mp4",
        size=5000,
        duration=30.0,
    )
    temp_db_session.add(video)
    temp_db_session.commit()

    clip = ClipSegment(
        video_id=video.id,
        start_seconds=1.0,
        end_seconds=5.0,
    )
    temp_db_session.add(clip)
    temp_db_session.commit()

    assert temp_db_session.query(ClipSegment).filter(ClipSegment.video_id == video.id).count() == 1

    temp_db_session.delete(video)
    temp_db_session.commit()

    assert temp_db_session.query(ClipSegment).filter(ClipSegment.video_id == video.id).count() == 0
