"""Tests for catalog service recursive scanning, upserting, and query filtering."""

import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base
from app.models.video import Video, VideoStatus
from app.services.catalog import CatalogService


class MockProbeService:
    """Mock probe service implementation satisfying VideoProbeInterface."""

    def __init__(
        self,
        metadata_map: dict[str, dict[str, Any] | Exception] | None = None,
    ) -> None:
        self.metadata_map: dict[str, dict[str, Any] | Exception] = metadata_map or {}
        self.call_count = 0

    def probe_video(self, video_path: Path) -> dict[str, Any]:
        self.call_count += 1
        name = video_path.name
        if name in self.metadata_map:
            val = self.metadata_map[name]
            if isinstance(val, Exception):
                raise val
            return val
        # Default mock probe result
        return {
            "format": {
                "duration": "100.0",
                "bit_rate": "1500000",
                "format_name": "mp4",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30/1",
                }
            ],
        }


@pytest.fixture
def temp_db() -> Generator[Session, None, None]:
    """Provide a clean isolated SQLite database session."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "catalog_test.db"
        engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(bind=engine)
        SessionTest = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionTest()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()


def test_catalog_recursive_scan_and_upsert(temp_db: Session, tmp_path: Path) -> None:
    """Ensure catalog recursively discovers videos, extracts metadata, and upserts."""
    # Setup directories
    sub_dir = tmp_path / "subfolder"
    sub_dir.mkdir()

    v1 = tmp_path / "video_a.mp4"
    v1.write_bytes(b"video a dummy bytes 12345")
    v2 = sub_dir / "video_b.mkv"
    v2.write_bytes(b"video b dummy bytes 67890")
    non_video = tmp_path / "readme.txt"
    non_video.write_text("not a video")

    probe_map: dict[str, dict[str, Any] | Exception] = {
        "video_a.mp4": {
            "format": {"duration": "120.5", "bit_rate": "2000000"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}
            ],
        },
        "video_b.mkv": {
            "format": {"duration": "350.2", "bit_rate": "3000000"},
            "streams": [
                {"codec_type": "video", "codec_name": "hevc", "width": 3840, "height": 2160}
            ],
        },
    }
    mock_probe = MockProbeService(probe_map)
    service = CatalogService(probe_service=mock_probe)

    # First scan
    summary = service.scan(db=temp_db, roots=[str(tmp_path)])
    assert summary.total_found == 2
    assert summary.added == 2
    assert summary.updated == 0
    assert summary.failed == 0
    assert len(summary.missing_roots) == 0

    records = temp_db.query(Video).all()
    assert len(records) == 2

    # Verify duration sorting (descending: video_b: 350.2 > video_a: 120.5)
    listing = service.list_videos(db=temp_db, sort_by="duration", order="desc")
    assert len(listing.items) == 2
    assert listing.items[0].filename == "video_b.mkv"
    assert listing.items[0].duration == 350.2
    assert listing.items[0].codec == "hevc"
    assert listing.items[0].status == VideoStatus.UNPROCESSED
    assert listing.items[1].filename == "video_a.mp4"
    assert listing.items[1].duration == 120.5

    # Second scan: upsert should update, not create duplicates
    summary2 = service.scan(db=temp_db, roots=[str(tmp_path)])
    assert summary2.total_found == 2
    assert summary2.added == 0
    assert summary2.updated == 2
    assert temp_db.query(Video).count() == 2


def test_catalog_preserves_workflow_status_on_rescan(temp_db: Session, tmp_path: Path) -> None:
    """Ensure rescanning does not overwrite user review statuses like clip_selected or discarded."""
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"content")

    mock_probe = MockProbeService(
        {
            "clip.mp4": {
                "format": {"duration": "45.0"},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
        }
    )
    service = CatalogService(probe_service=mock_probe)

    # Initial scan
    service.scan(db=temp_db, roots=[str(tmp_path)])
    video = temp_db.query(Video).first()
    assert video is not None
    assert video.status == VideoStatus.UNPROCESSED.value

    # User updates status in review workflow
    video.status = VideoStatus.CLIP_SELECTED.value
    temp_db.commit()

    # Rescan
    service.scan(db=temp_db, roots=[str(tmp_path)])
    refreshed = temp_db.query(Video).first()
    assert refreshed is not None
    assert refreshed.status == VideoStatus.CLIP_SELECTED.value


def test_catalog_safe_missing_roots(temp_db: Session, tmp_path: Path) -> None:
    """Ensure nonexistent roots are reported without raising errors or deleting rows."""
    existing_dir = tmp_path / "valid"
    existing_dir.mkdir()
    (existing_dir / "test.mp4").write_bytes(b"sample")

    service = CatalogService(probe_service=MockProbeService())
    # First populate 1 record
    service.scan(db=temp_db, roots=[str(existing_dir)])
    assert temp_db.query(Video).count() == 1

    # Scan with non-existent root
    missing_dir = tmp_path / "nonexistent_folder_abc"
    summary = service.scan(db=temp_db, roots=[str(missing_dir), str(existing_dir)])

    assert str(missing_dir) in summary.missing_roots
    assert str(existing_dir.resolve()) in summary.scanned_roots
    # Row must NOT be deleted!
    assert temp_db.query(Video).count() == 1


def test_catalog_safe_malformed_probe_results(temp_db: Session, tmp_path: Path) -> None:
    """Ensure malformed/corrupted probe does not crash scan or delete existing rows."""
    bad_video = tmp_path / "corrupted.mp4"
    bad_video.write_bytes(b"corrupt header")

    mock_probe = MockProbeService(
        {
            "corrupted.mp4": RuntimeError("ffprobe: Invalid data found"),
        }
    )
    service = CatalogService(probe_service=mock_probe)

    summary = service.scan(db=temp_db, roots=[str(tmp_path)])
    assert summary.total_found == 1
    assert summary.failed == 1
    assert summary.added == 1

    row = temp_db.query(Video).filter(Video.filename == "corrupted.mp4").first()
    assert row is not None
    assert row.duration is None
    assert row.scan_error is not None
    assert "Invalid data found" in row.scan_error
    assert row.status == VideoStatus.UNPROCESSED.value


def test_catalog_list_filtering_and_pagination(temp_db: Session, tmp_path: Path) -> None:
    """Ensure list_videos filters by status and supports pagination."""
    # Seed videos with different statuses and durations
    for i, dur in enumerate([10.0, 50.0, 30.0, 100.0, 5.0]):
        status = VideoStatus.CLIP_SELECTED.value if i % 2 == 0 else VideoStatus.UNPROCESSED.value
        v = Video(
            path=f"/media/videos/video_{i}.mp4",
            filename=f"video_{i}.mp4",
            size=1000 + i,
            duration=dur,
            status=status,
        )
        temp_db.add(v)
    temp_db.commit()

    service = CatalogService()

    # Query all, duration desc
    res_all = service.list_videos(db=temp_db, page=1, page_size=10)
    assert res_all.total == 5
    durations = [item.duration for item in res_all.items]
    assert durations == [100.0, 50.0, 30.0, 10.0, 5.0]

    # Query with status filter: CLIP_SELECTED (i = 0, 2, 4 -> dur: 10.0, 30.0, 5.0)
    res_filtered = service.list_videos(
        db=temp_db, status=VideoStatus.CLIP_SELECTED, page=1, page_size=10
    )
    assert res_filtered.total == 3
    filtered_durations = [item.duration for item in res_filtered.items]
    assert filtered_durations == [30.0, 10.0, 5.0]

    # Pagination: page_size=2
    p1 = service.list_videos(db=temp_db, page=1, page_size=2)
    assert len(p1.items) == 2
    assert p1.total_pages == 3
    assert p1.items[0].duration == 100.0
    assert p1.items[1].duration == 50.0

    p2 = service.list_videos(db=temp_db, page=2, page_size=2)
    assert len(p2.items) == 2
    assert p2.items[0].duration == 30.0
    assert p2.items[1].duration == 10.0


def test_catalog_filesystem_is_read_only(temp_db: Session, tmp_path: Path) -> None:
    """Verify that scanning leaves all original files and directory structure untouched."""
    video = tmp_path / "original.mp4"
    content = b"original media binary content"
    video.write_bytes(content)
    mtime_before = video.stat().st_mtime_ns

    service = CatalogService(probe_service=MockProbeService())
    service.scan(db=temp_db, roots=[str(tmp_path)])

    assert video.exists()
    assert video.read_bytes() == content
    assert video.stat().st_mtime_ns == mtime_before
