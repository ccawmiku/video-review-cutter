"""Integration tests for video catalog API endpoints."""

import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models.video import Video, VideoStatus
from app.services.catalog import catalog_service


@pytest.fixture
def client_with_db() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    """FastAPI TestClient with isolated SQLite database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test_api.db"
        engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
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


def test_api_scan_and_status(
    client_with_db: tuple[TestClient, sessionmaker[Session]], tmp_path: Path
) -> None:
    """Test triggering scan via API and inspecting scan status."""
    client, _ = client_with_db

    # Create dummy video files
    v1 = tmp_path / "clip1.mp4"
    v1.write_bytes(b"content 1")
    v2 = tmp_path / "clip2.mkv"
    v2.write_bytes(b"content 2")

    # Mock the probe service on catalog_service
    class MockProbe:
        def probe_video(self, video_path: Path) -> dict[str, Any]:
            dur = "60.0" if "clip1" in video_path.name else "120.0"
            return {
                "format": {"duration": dur, "bit_rate": "1000000"},
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720}
                ],
            }

    original_probe = catalog_service.probe_service
    catalog_service.probe_service = MockProbe()

    try:
        # Trigger scan
        response = client.post("/api/videos/scan", json={"roots": [str(tmp_path)]})
        assert response.status_code == 200
        data = response.json()
        assert data["total_found"] == 2
        assert data["added"] == 2
        assert data["failed"] == 0

        # Inspect status
        status_res = client.get("/api/videos/scan/status")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["has_scanned"] is True
        assert status_data["last_scan"]["total_found"] == 2

        # Catalog alias route inspection
        catalog_status = client.get("/api/catalog/scan/status")
        assert catalog_status.status_code == 200
        assert catalog_status.json()["has_scanned"] is True
    finally:
        catalog_service.probe_service = original_probe


def test_api_list_videos_sorting_and_filtering(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """Test /api/videos sorting by duration descending and status filtering."""
    client, session_factory = client_with_db
    db = session_factory()

    # Populate dummy videos
    db.add(
        Video(
            path="/media/v_short.mp4",
            filename="v_short.mp4",
            size=1000,
            duration=15.0,
            status=VideoStatus.UNPROCESSED.value,
        )
    )
    db.add(
        Video(
            path="/media/v_long.mp4",
            filename="v_long.mp4",
            size=5000,
            duration=300.0,
            status=VideoStatus.CLIP_SELECTED.value,
        )
    )
    db.add(
        Video(
            path="/media/v_mid.mp4",
            filename="v_mid.mp4",
            size=2500,
            duration=90.0,
            status=VideoStatus.UNPROCESSED.value,
        )
    )
    db.commit()
    db.close()

    # List all: should be sorted by duration descending (300.0 -> 90.0 -> 15.0)
    res = client.get("/api/videos")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    durations = [item["duration"] for item in data["items"]]
    assert durations == [300.0, 90.0, 15.0]
    assert data["items"][0]["filename"] == "v_long.mp4"

    # Filter by status = unprocessed (should return v_mid: 90.0, v_short: 15.0)
    res_unprocessed = client.get("/api/videos?status=unprocessed")
    assert res_unprocessed.status_code == 200
    data_unproc = res_unprocessed.json()
    assert data_unproc["total"] == 2
    assert [i["filename"] for i in data_unproc["items"]] == ["v_mid.mp4", "v_short.mp4"]

    # Filter by status = clip_selected
    res_clip = client.get("/api/videos?status=clip_selected")
    assert res_clip.status_code == 200
    data_clip = res_clip.json()
    assert data_clip["total"] == 1
    assert data_clip["items"][0]["filename"] == "v_long.mp4"


def test_api_pagination_and_get_by_id(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """Test pagination parameters and single video lookup by ID."""
    client, session_factory = client_with_db
    db = session_factory()

    created_ids: list[int] = []
    for i in range(1, 6):
        v = Video(
            path=f"/media/item_{i}.mp4",
            filename=f"item_{i}.mp4",
            size=1000 * i,
            duration=float(i * 10),
            status=VideoStatus.UNPROCESSED.value,
        )
        db.add(v)
        db.flush()
        created_ids.append(v.id)
    db.commit()
    db.close()

    # Page 1 with size 2
    res_p1 = client.get("/api/videos?page=1&page_size=2")
    assert res_p1.status_code == 200
    p1 = res_p1.json()
    assert p1["total"] == 5
    assert p1["page"] == 1
    assert p1["page_size"] == 2
    assert p1["total_pages"] == 3
    assert len(p1["items"]) == 2
    assert p1["items"][0]["duration"] == 50.0

    # Get by ID
    target_id = created_ids[0]
    res_item = client.get(f"/api/videos/{target_id}")
    assert res_item.status_code == 200
    item_data = res_item.json()
    assert item_data["id"] == target_id
    assert item_data["filename"] == "item_1.mp4"

    # Nonexistent ID -> 404
    res_not_found = client.get("/api/videos/999999")
    assert res_not_found.status_code == 404
