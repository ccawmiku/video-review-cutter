"""Integration and unit tests for video preview streaming endpoint."""

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app
from app.models.video import Video, VideoStatus
from app.services.streaming import (
    guess_video_mime_type,
    parse_range_header,
    streaming_service,
)


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


def test_preview_full_body_200(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test full 200 response without Range header and HEAD metadata."""
    client, session_factory = client_with_db
    db = session_factory()

    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    sample_content = b"0123456789ABCDEF" * 64  # 1024 bytes
    video_file = video_dir / "preview_sample.mp4"
    video_file.write_bytes(sample_content)

    monkeypatch.setattr(settings, "video_roots", [str(video_dir)])

    v = Video(
        path=str(video_file.resolve()),
        filename="preview_sample.mp4",
        size=len(sample_content),
        duration=60.0,
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    video_id = v.id
    db.close()

    # GET full content
    response = client.get(f"/api/videos/{video_id}/preview")
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["content-length"] == "1024"
    assert response.headers["accept-ranges"] == "bytes"
    assert "etag" in response.headers
    assert response.content == sample_content

    # HEAD request returns metadata with empty body
    head_response = client.head(f"/api/videos/{video_id}/preview")
    assert head_response.status_code == 200
    assert head_response.headers["content-length"] == "1024"
    assert head_response.headers["content-type"] == "video/mp4"
    assert head_response.content == b""

    # Alias /stream route returns identical full content
    stream_response = client.get(f"/api/videos/{video_id}/stream")
    assert stream_response.status_code == 200
    assert stream_response.content == sample_content

    # Catalog alias route prefix
    catalog_response = client.get(f"/api/catalog/{video_id}/preview")
    assert catalog_response.status_code == 200
    assert catalog_response.content == sample_content


def test_preview_valid_ranges_206(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test valid single HTTP Range requests returning 206 Partial Content."""
    client, session_factory = client_with_db
    db = session_factory()

    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    sample_content = b"0123456789" * 100  # 1000 bytes (offsets 0-999)
    video_file = video_dir / "range_test.mp4"
    video_file.write_bytes(sample_content)

    monkeypatch.setattr(settings, "video_roots", [str(video_dir)])

    v = Video(
        path=str(video_file.resolve()),
        filename="range_test.mp4",
        size=1000,
        duration=10.0,
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    video_id = v.id
    db.close()

    # 1. Closed range: bytes=0-49 (50 bytes)
    res1 = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=0-49"})
    assert res1.status_code == 206
    assert res1.headers["content-range"] == "bytes 0-49/1000"
    assert res1.headers["content-length"] == "50"
    assert res1.headers["accept-ranges"] == "bytes"
    assert res1.content == sample_content[0:50]

    # 2. Intermediate range: bytes=100-199 (100 bytes)
    res2 = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=100-199"})
    assert res2.status_code == 206
    assert res2.headers["content-range"] == "bytes 100-199/1000"
    assert res2.headers["content-length"] == "100"
    assert res2.content == sample_content[100:200]

    # 3. Open-ended range from offset: bytes=800- (200 bytes)
    res3 = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=800-"})
    assert res3.status_code == 206
    assert res3.headers["content-range"] == "bytes 800-999/1000"
    assert res3.headers["content-length"] == "200"
    assert res3.content == sample_content[800:1000]

    # 4. Suffix range: bytes=-50 (last 50 bytes)
    res4 = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=-50"})
    assert res4.status_code == 206
    assert res4.headers["content-range"] == "bytes 950-999/1000"
    assert res4.headers["content-length"] == "50"
    assert res4.content == sample_content[950:1000]

    # 5. Single byte: bytes=0-0 (1 byte)
    res5 = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=0-0"})
    assert res5.status_code == 206
    assert res5.headers["content-range"] == "bytes 0-0/1000"
    assert res5.headers["content-length"] == "1"
    assert res5.content == sample_content[0:1]

    # 6. End beyond file size: bytes=900-5000 (clamped to 999)
    res6 = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=900-5000"})
    assert res6.status_code == 206
    assert res6.headers["content-range"] == "bytes 900-999/1000"
    assert res6.headers["content-length"] == "100"
    assert res6.content == sample_content[900:1000]

    # 7. HEAD request with valid range
    head_res = client.head(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=0-49"})
    assert head_res.status_code == 206
    assert head_res.headers["content-range"] == "bytes 0-49/1000"
    assert head_res.headers["content-length"] == "50"
    assert head_res.content == b""


def test_preview_invalid_and_unsatisfiable_ranges_416(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test invalid and unsatisfiable ranges returning 416 Range Not Satisfiable."""
    client, session_factory = client_with_db
    db = session_factory()

    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    sample_content = b"ABCDEFGHIJ" * 10  # 100 bytes
    video_file = video_dir / "invalid_range.mp4"
    video_file.write_bytes(sample_content)

    monkeypatch.setattr(settings, "video_roots", [str(video_dir)])

    v = Video(
        path=str(video_file.resolve()),
        filename="invalid_range.mp4",
        size=100,
        duration=5.0,
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    video_id = v.id
    db.close()

    # Offset beyond EOF
    res_eof = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=100-"})
    assert res_eof.status_code == 416
    assert res_eof.headers["content-range"] == "bytes */100"
    assert res_eof.headers["content-length"] == "0"

    # Start beyond EOF
    res_far = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=500-600"})
    assert res_far.status_code == 416
    assert res_far.headers["content-range"] == "bytes */100"

    # Inverted range (start > end)
    res_inv = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=50-20"})
    assert res_inv.status_code == 416
    assert res_inv.headers["content-range"] == "bytes */100"

    # Non-numeric range
    res_alpha = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=abc-def"})
    assert res_alpha.status_code == 416
    assert res_alpha.headers["content-range"] == "bytes */100"

    # Suffix length zero or negative
    res_zero = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=-0"})
    assert res_zero.status_code == 416
    assert res_zero.headers["content-range"] == "bytes */100"

    # Multi-range (only single range supported)
    res_multi = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "bytes=0-10,20-30"})
    assert res_multi.status_code == 416
    assert res_multi.headers["content-range"] == "bytes */100"

    # Non-bytes unit
    res_unit = client.get(f"/api/videos/{video_id}/preview", headers={"Range": "items=0-10"})
    assert res_unit.status_code == 416
    assert res_unit.headers["content-range"] == "bytes */100"


def test_preview_missing_video_and_missing_file_404(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 404 responses for nonexistent video ID, missing file on disk, and non-file."""
    client, session_factory = client_with_db
    db = session_factory()

    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    monkeypatch.setattr(settings, "video_roots", [str(video_dir)])

    # 1. Non-existent video ID
    res_no_id = client.get("/api/videos/99999/preview")
    assert res_no_id.status_code == 404
    assert "not found" in res_no_id.json()["detail"].lower()

    # 2. Video record exists in DB, but file missing on disk
    missing_file = video_dir / "deleted_video.mp4"
    v_missing = Video(
        path=str(missing_file.resolve()),
        filename="deleted_video.mp4",
        size=500,
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(v_missing)
    db.commit()
    db.refresh(v_missing)
    missing_id = v_missing.id

    res_missing_file = client.get(f"/api/videos/{missing_id}/preview")
    assert res_missing_file.status_code == 404
    assert "not found" in res_missing_file.json()["detail"].lower()

    # 3. Path in DB points to a directory instead of a regular file
    subdir = video_dir / "some_dir.mp4"
    subdir.mkdir()
    v_dir = Video(
        path=str(subdir.resolve()),
        filename="some_dir.mp4",
        size=0,
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(v_dir)
    db.commit()
    db.refresh(v_dir)
    dir_id = v_dir.id

    res_dir = client.get(f"/api/videos/{dir_id}/preview")
    assert res_dir.status_code == 404
    assert "regular file" in res_dir.json()["detail"].lower()

    db.close()


def test_preview_path_safety_configured_root_escapes_403(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test rejection of paths escaping configured VIDEO_ROOTS with 403 Forbidden."""
    client, session_factory = client_with_db
    db = session_factory()

    # Configured allowed root
    video_dir = tmp_path / "allowed_videos"
    video_dir.mkdir()
    monkeypatch.setattr(settings, "video_roots", [str(video_dir)])

    # Sensitive/outside directory
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    outside_file = outside_dir / "confidential.mp4"
    outside_file.write_bytes(b"SECRET DATA")

    # DB record points directly to outside file (configured-root escape)
    v_outside = Video(
        path=str(outside_file.resolve()),
        filename="confidential.mp4",
        size=11,
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(v_outside)
    db.commit()
    db.refresh(v_outside)
    outside_id = v_outside.id

    res_escape = client.get(f"/api/videos/{outside_id}/preview")
    assert res_escape.status_code == 403
    assert "outside configured" in res_escape.json()["detail"].lower()

    # Traversal relative path stored in DB
    traversal_path = str(video_dir / ".." / "outside_dir" / "confidential.mp4")
    v_traversal = Video(
        path=traversal_path,
        filename="traversal.mp4",
        size=11,
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(v_traversal)
    db.commit()
    db.refresh(v_traversal)
    traversal_id = v_traversal.id

    res_trav = client.get(f"/api/videos/{traversal_id}/preview")
    assert res_trav.status_code == 403

    # No valid configured roots available
    monkeypatch.setattr(settings, "video_roots", [str(tmp_path / "nonexistent_root")])
    res_no_roots = client.get(f"/api/videos/{outside_id}/preview")
    assert res_no_roots.status_code == 403

    db.close()


def test_preview_path_safety_symlink_escapes_403(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test rejection of symlink traversal escaping configured VIDEO_ROOTS."""
    client, session_factory = client_with_db
    db = session_factory()

    video_dir = tmp_path / "allowed_videos"
    video_dir.mkdir()
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()

    outside_file = outside_dir / "target.mp4"
    outside_file.write_bytes(b"OUTSIDE_SECRET_DATA")

    symlink_file = video_dir / "escape_symlink.mp4"

    monkeypatch.setattr(settings, "video_roots", [str(video_dir)])

    # Try creating real symlink if permitted (e.g. on Linux CI)
    can_symlink = False
    try:
        os.symlink(str(outside_file.resolve()), str(symlink_file))
        can_symlink = True
    except OSError:
        pass

    if can_symlink:
        v_sym = Video(
            path=str(symlink_file.resolve()),
            filename="escape_symlink.mp4",
            size=len(b"OUTSIDE_SECRET_DATA"),
            status=VideoStatus.UNPROCESSED.value,
        )
        db.add(v_sym)
        db.commit()
        db.refresh(v_sym)
        sym_id = v_sym.id

        res_sym = client.get(f"/api/videos/{sym_id}/preview")
        assert res_sym.status_code == 403
        assert "outside configured" in res_sym.json()["detail"].lower()
    else:
        # Fallback simulation for OS environments without symlink creation privileges
        mock_file = video_dir / "fake_symlink.mp4"
        mock_file.write_bytes(b"PLACEHOLDER")

        v_mock = Video(
            path=str(mock_file.resolve()),
            filename="fake_symlink.mp4",
            size=len(b"PLACEHOLDER"),
            status=VideoStatus.UNPROCESSED.value,
        )
        db.add(v_mock)
        db.commit()
        db.refresh(v_mock)
        mock_id = v_mock.id

        orig_resolve = Path.resolve
        orig_is_symlink = Path.is_symlink

        def mock_resolve(self: Path, *args: object, **kwargs: object) -> Path:
            if self.name == "fake_symlink.mp4":
                return outside_file.resolve()
            return orig_resolve(self, *args, **kwargs)

        def mock_is_symlink(self: Path) -> bool:
            if self.name == "fake_symlink.mp4":
                return True
            return orig_is_symlink(self)

        with (
            patch.object(Path, "is_symlink", mock_is_symlink),
            patch.object(Path, "resolve", mock_resolve),
        ):
            res_sym = client.get(f"/api/videos/{mock_id}/preview")
            assert res_sym.status_code == 403
            assert (
                "symlink escape" in res_sym.json()["detail"].lower()
                or "outside configured" in res_sym.json()["detail"].lower()
            )

        db.close()


@pytest.mark.asyncio
async def test_preview_chunked_streaming_no_whole_file_buffering(tmp_path: Path) -> None:
    """Test that stream_file_chunks reads in bounded chunks without loading the whole file."""
    test_file = tmp_path / "streaming_chunks.bin"
    # Write 256 bytes
    test_file.write_bytes(b"X" * 256)

    # Use a small chunk size of 64 bytes
    custom_service = streaming_service.__class__(chunk_size=64)

    chunks: list[bytes] = []
    async for chunk in custom_service.stream_file_chunks(test_file, start=0, end=255):
        chunks.append(chunk)

    # 256 / 64 = 4 chunks
    assert len(chunks) == 4
    for chunk in chunks:
        assert len(chunk) == 64
        assert chunk == b"X" * 64

    # Range slice: start=10, end=79 (70 bytes -> 64 + 6)
    sliced_chunks: list[bytes] = []
    async for chunk in custom_service.stream_file_chunks(test_file, start=10, end=79):
        sliced_chunks.append(chunk)

    assert len(sliced_chunks) == 2
    assert len(sliced_chunks[0]) == 64
    assert len(sliced_chunks[1]) == 6
    assert b"".join(sliced_chunks) == b"X" * 70


def test_guess_video_mime_types() -> None:
    """Test accurate MIME detection for video file formats."""
    assert guess_video_mime_type(Path("video.mp4")) == "video/mp4"
    assert guess_video_mime_type(Path("video.mkv")) == "video/x-matroska"
    assert guess_video_mime_type(Path("video.webm")) == "video/webm"
    assert guess_video_mime_type(Path("video.mov")) == "video/quicktime"
    assert guess_video_mime_type(Path("video.flv")) == "video/x-flv"
    assert guess_video_mime_type(Path("video.wmv")) == "video/x-ms-wmv"
    assert guess_video_mime_type(Path("video.avi")) == "video/x-msvideo"
    assert guess_video_mime_type(Path("video.ts")) == "video/mp2t"
    assert guess_video_mime_type(Path("video.m4v")) == "video/mp4"


def test_parse_range_header_unit() -> None:
    """Test parse_range_header unit logic."""
    assert parse_range_header(None, 100) is None
    assert parse_range_header("", 100) is None
    assert parse_range_header("bytes=0-49", 100) == (0, 49)
    assert parse_range_header("bytes=50-", 100) == (50, 99)
    assert parse_range_header("bytes=-10", 100) == (90, 99)
