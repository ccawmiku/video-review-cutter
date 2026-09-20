"""Focused temporary-directory tests for video discard workflow.

Validates:
- Success with atomic rename and cross-filesystem fallback
- Deterministic collision avoidance without overwriting
- Invalid root rejection and traversal protection
- Symlink escape protection
- Failure rollback (preserving source and DB status)
- Non-regular file rejection and missing file/video handling
- Already-discarded idempotence guard
- Compatible schema initialization on pre-existing database tables
"""

from __future__ import annotations

import errno
import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import Base, get_db, migrate_schema_compatibility
from app.main import app
from app.models.video import Video, VideoStatus


@pytest.fixture
def client_with_db() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    """FastAPI TestClient with isolated in-memory SQLite database."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    try:
        yield test_client, TestingSessionLocal
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_discard_success_same_filesystem(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test successful discard using atomic rename on the same filesystem."""
    client, session_factory = client_with_db
    video_root = tmp_path / "videos"
    video_root.mkdir(parents=True)
    discarded_root = tmp_path / "discarded"
    discarded_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "discarded_dir", discarded_root)

    source_file = video_root / "sample_video.mp4"
    source_file.write_bytes(b"dummy video content 12345")

    db = session_factory()
    video = Video(
        path=str(source_file),
        filename=source_file.name,
        size=len(b"dummy video content 12345"),
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()

    resp = client.post(f"/api/videos/{video_id}/discard")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "discarded"
    assert data["decision"] == "discarded"
    assert data["filename"] == "sample_video.mp4"
    expected_dest = discarded_root / "sample_video.mp4"
    assert data["path"] == str(expected_dest)
    assert data["current_path"] == str(expected_dest)
    assert data["original_path"] == str(source_file)
    assert data["discarded_at"] is not None
    assert data["move_metadata"] is not None
    assert data["move_metadata"]["source_path"] == str(source_file)
    assert data["move_metadata"]["destination_path"] == str(expected_dest)
    assert data["move_metadata"]["strategy"] == "atomic_rename"

    # Verify source was removed and destination exists with intact content
    assert not source_file.exists()
    assert expected_dest.exists()
    assert expected_dest.read_bytes() == b"dummy video content 12345"

    # Verify database state
    db = session_factory()
    updated = db.query(Video).filter(Video.id == video_id).first()
    assert updated is not None
    assert updated.status == VideoStatus.DISCARDED.value
    assert updated.path == str(expected_dest)
    assert updated.original_path == str(source_file)
    assert updated.discarded_at is not None
    db.close()


def test_discard_success_cross_device_fallback(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test successful discard fallback when atomic rename triggers EXDEV."""
    client, session_factory = client_with_db
    video_root = tmp_path / "videos"
    video_root.mkdir(parents=True)
    discarded_root = tmp_path / "discarded"
    discarded_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "discarded_dir", discarded_root)

    source_file = video_root / "cross_fs_video.mkv"
    payload_content = b"Cross device test content bytes" * 100
    source_file.write_bytes(payload_content)

    db = session_factory()
    video = Video(
        path=str(source_file),
        filename=source_file.name,
        size=len(payload_content),
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()

    # Simulate cross-device move by having os.replace fail on first attempt with EXDEV
    real_replace = os.replace

    def mock_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        src_p = Path(src)
        # If source is the original source file, trigger EXDEV
        if src_p == source_file:
            raise OSError(errno.EXDEV, "Cross-device link")
        real_replace(src, dst)

    with patch("os.replace", side_effect=mock_replace):
        resp = client.post(
            f"/api/catalog/{video_id}/discard",
            json={"reason": "Testing cross device move fallback"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "discarded"
    assert data["move_metadata"]["strategy"] == "cross_device_copy"
    assert data["move_metadata"]["reason"] == "Testing cross device move fallback"

    expected_dest = discarded_root / "cross_fs_video.mkv"
    assert not source_file.exists()
    assert expected_dest.exists()
    assert expected_dest.read_bytes() == payload_content


def test_discard_deterministic_collisions(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that existing files are never overwritten and deterministic suffixes are assigned."""
    client, session_factory = client_with_db
    video_root = tmp_path / "videos"
    video_root.mkdir(parents=True)
    discarded_root = tmp_path / "discarded"
    discarded_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "discarded_dir", discarded_root)

    # Pre-populate collisions in discarded_dir
    collision_0 = discarded_root / "item.mp4"
    collision_0.write_bytes(b"existing version 0")
    collision_1 = discarded_root / "item_1.mp4"
    collision_1.write_bytes(b"existing version 1")

    # New source file
    source_file = video_root / "item.mp4"
    source_file.write_bytes(b"new video to discard")

    db = session_factory()
    video = Video(
        path=str(source_file),
        filename=source_file.name,
        size=len(b"new video to discard"),
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()

    resp = client.post(f"/api/videos/{video_id}/discard")
    assert resp.status_code == 200
    data = resp.json()

    # Must be deterministically named item_2.mp4
    expected_dest = discarded_root / "item_2.mp4"
    assert data["filename"] == "item_2.mp4"
    assert data["path"] == str(expected_dest)

    # Existing files must remain completely untouched
    assert collision_0.read_bytes() == b"existing version 0"
    assert collision_1.read_bytes() == b"existing version 1"
    assert expected_dest.read_bytes() == b"new video to discard"
    assert not source_file.exists()


def test_discard_invalid_roots_and_traversal(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test rejection of files located outside VIDEO_ROOTS and path traversal attempts."""
    client, session_factory = client_with_db
    video_root = tmp_path / "videos"
    video_root.mkdir(parents=True)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir(parents=True)
    discarded_root = tmp_path / "discarded"
    discarded_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "discarded_dir", discarded_root)

    # Video located outside configured root
    outside_file = outside_dir / "secret.mp4"
    outside_file.write_bytes(b"secret outside video")

    db = session_factory()
    video_outside = Video(
        path=str(outside_file),
        filename=outside_file.name,
        size=len(b"secret outside video"),
    )
    db.add(video_outside)
    db.commit()
    db.refresh(video_outside)
    video_outside_id = video_outside.id

    # Video path with traversal attempt
    traversal_path = video_root / ".." / "outside" / "secret.mp4"
    video_traversal = Video(
        path=str(traversal_path),
        filename="secret.mp4",
        size=len(b"secret outside video"),
    )
    db.add(video_traversal)
    db.commit()
    db.refresh(video_traversal)
    video_traversal_id = video_traversal.id
    db.close()

    # 1. Outside root attempt
    resp1 = client.post(f"/api/videos/{video_outside_id}/discard")
    assert resp1.status_code == 403
    assert "outside configured video roots" in resp1.json()["detail"]
    assert outside_file.exists()

    # 2. Traversal attempt
    resp2 = client.post(f"/api/videos/{video_traversal_id}/discard")
    assert resp2.status_code == 403
    assert outside_file.exists()

    # Verify DB statuses were not updated to discarded
    db = session_factory()
    v1 = db.query(Video).filter(Video.id == video_outside_id).first()
    v2 = db.query(Video).filter(Video.id == video_traversal_id).first()
    assert v1.status == VideoStatus.UNPROCESSED.value
    assert v2.status == VideoStatus.UNPROCESSED.value
    db.close()


def test_discard_symlink_escape(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test detection and rejection of symlinks escaping configured video roots."""
    client, session_factory = client_with_db
    video_root = tmp_path / "videos"
    video_root.mkdir(parents=True)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir(parents=True)
    discarded_root = tmp_path / "discarded"
    discarded_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "discarded_dir", discarded_root)

    target_outside = outside_dir / "target.mp4"
    target_outside.write_bytes(b"target file content")
    symlink_file = video_root / "sym_escape.mp4"

    # Create real symlink or mock if OS permissions restrict symlink creation
    can_symlink = True
    try:
        symlink_file.symlink_to(target_outside)
    except (OSError, NotImplementedError):
        can_symlink = False
        symlink_file.write_bytes(b"dummy")

    db = session_factory()
    video = Video(
        path=str(symlink_file),
        filename=symlink_file.name,
        size=len(b"target file content"),
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()

    if can_symlink:
        resp = client.post(f"/api/videos/{video_id}/discard")
        assert resp.status_code == 403
        assert (
            "symlink escape" in resp.json()["detail"].lower()
            or "outside configured" in resp.json()["detail"].lower()
        )
        assert target_outside.exists()
        assert symlink_file.exists()
    else:
        # On Windows environments without symlink privilege, mock only for the fake symlink file
        orig_resolve = Path.resolve
        orig_is_symlink = Path.is_symlink

        def mock_resolve(self: Path, strict: bool = False) -> Path:
            if self.name == "sym_escape.mp4":
                return target_outside.resolve(strict=strict)
            return orig_resolve(self, strict=strict)

        def mock_is_symlink(self: Path) -> bool:
            if self.name == "sym_escape.mp4":
                return True
            return orig_is_symlink(self)

        with (
            patch.object(Path, "is_symlink", mock_is_symlink),
            patch.object(Path, "resolve", mock_resolve),
        ):
            resp = client.post(f"/api/videos/{video_id}/discard")
            assert resp.status_code == 403
            assert (
                "symlink escape" in resp.json()["detail"].lower()
                or "outside configured" in resp.json()["detail"].lower()
            )

    # Verify source was not removed or altered
    assert target_outside.exists()
    db = session_factory()
    v = db.query(Video).filter(Video.id == video_id).first()
    assert v.status == VideoStatus.UNPROCESSED.value
    db.close()


def test_discard_failure_rollback(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that source file and DB status are preserved on move failure or DB error."""
    client, session_factory = client_with_db
    video_root = tmp_path / "videos"
    video_root.mkdir(parents=True)
    discarded_root = tmp_path / "discarded"
    discarded_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "discarded_dir", discarded_root)

    source_file = video_root / "fail_video.mp4"
    source_file.write_bytes(b"content before failure")

    db = session_factory()
    video = Video(
        path=str(source_file),
        filename=source_file.name,
        size=len(b"content before failure"),
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()

    # 1. Simulate move failure
    with patch(
        "app.services.discard.move_file_safely",
        side_effect=OSError("Simulated disk error"),
    ):
        resp = client.post(f"/api/videos/{video_id}/discard")
        assert resp.status_code == 500

    # Source must still exist intact, and DB status must remain unprocessed
    assert source_file.exists()
    assert source_file.read_bytes() == b"content before failure"
    db = session_factory()
    v = db.query(Video).filter(Video.id == video_id).first()
    assert v.status == VideoStatus.UNPROCESSED.value
    assert v.path == str(source_file)
    db.close()

    # 2. Simulate database commit failure after file move: should rollback file to source
    with patch.object(Session, "commit", side_effect=RuntimeError("Simulated DB commit crash")):
        resp2 = client.post(f"/api/videos/{video_id}/discard")
        assert resp2.status_code == 500

    # Source must be preserved / restored!
    assert source_file.exists()
    assert source_file.read_bytes() == b"content before failure"


def test_discard_non_regular_file_and_missing(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test rejection when video path is a directory or missing from disk."""
    client, session_factory = client_with_db
    video_root = tmp_path / "videos"
    video_root.mkdir(parents=True)
    discarded_root = tmp_path / "discarded"
    discarded_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "discarded_dir", discarded_root)

    # Subdirectory pretending to be a video
    sub_dir = video_root / "not_a_file.mp4"
    sub_dir.mkdir()

    # Nonexistent file path
    missing_file = video_root / "missing.mp4"

    db = session_factory()
    v_dir = Video(path=str(sub_dir), filename=sub_dir.name, size=0)
    v_missing = Video(path=str(missing_file), filename=missing_file.name, size=0)
    db.add_all([v_dir, v_missing])
    db.commit()
    db.refresh(v_dir)
    db.refresh(v_missing)
    dir_id, missing_id = v_dir.id, v_missing.id
    db.close()

    # Directory rejection
    resp_dir = client.post(f"/api/videos/{dir_id}/discard")
    assert resp_dir.status_code == 400
    assert "regular file" in resp_dir.json()["detail"]

    # Missing file rejection
    resp_missing = client.post(f"/api/videos/{missing_id}/discard")
    assert resp_missing.status_code == 404
    assert "not found on disk" in resp_missing.json()["detail"]

    # Non-existent DB video ID
    resp_notfound = client.post("/api/videos/999999/discard")
    assert resp_notfound.status_code == 404


def test_discard_already_discarded_guard(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that attempting to discard an already discarded video is rejected."""
    client, session_factory = client_with_db
    video_root = tmp_path / "videos"
    video_root.mkdir(parents=True)
    discarded_root = tmp_path / "discarded"
    discarded_root.mkdir(parents=True)

    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "discarded_dir", discarded_root)

    source_file = video_root / "double_discard.mp4"
    source_file.write_bytes(b"content")

    db = session_factory()
    video = Video(
        path=str(source_file),
        filename=source_file.name,
        size=len(b"content"),
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()

    # First discard succeeds
    resp1 = client.post(f"/api/videos/{video_id}/discard")
    assert resp1.status_code == 200

    # Second discard fails with 400
    resp2 = client.post(f"/api/videos/{video_id}/discard")
    assert resp2.status_code == 400
    assert "already discarded" in resp2.json()["detail"]


def test_schema_initialization_compatibility(tmp_path: Path) -> None:
    """Test that migrate_schema_compatibility seamlessly adds columns to pre-existing tables."""
    db_file = tmp_path / "legacy.db"
    legacy_engine = create_engine(f"sqlite:///{db_file}")

    # Create an old version of 'videos' table without original_path, discarded_at, move_metadata
    with legacy_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path VARCHAR(1024) NOT NULL UNIQUE,
                    filename VARCHAR(255) NOT NULL,
                    size BIGINT NOT NULL,
                    duration FLOAT,
                    status VARCHAR(32) NOT NULL DEFAULT 'unprocessed',
                    width INTEGER,
                    height INTEGER,
                    codec VARCHAR(64),
                    fps FLOAT,
                    bit_rate BIGINT,
                    scan_error VARCHAR(1024),
                    scan_metadata JSON,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    last_scanned_at DATETIME NOT NULL
                )
                """
            )
        )

    # Verify legacy columns initially
    inspector_before = inspect(legacy_engine)
    cols_before = {col["name"] for col in inspector_before.get_columns("videos")}
    assert "original_path" not in cols_before
    assert "discarded_at" not in cols_before
    assert "move_metadata" not in cols_before

    # Run migration
    migrate_schema_compatibility(target_engine=legacy_engine)

    # Verify newly added columns
    inspector_after = inspect(legacy_engine)
    cols_after = {col["name"] for col in inspector_after.get_columns("videos")}
    assert "original_path" in cols_after
    assert "discarded_at" in cols_after
    assert "move_metadata" in cols_after

    legacy_engine.dispose()
