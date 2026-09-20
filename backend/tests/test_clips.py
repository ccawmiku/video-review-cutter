"""Focused integration tests for clip segment CRUD, ordering, validation, and review decisions."""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models.clip import ClipSegment
from app.models.video import Video, VideoStatus


@pytest.fixture
def client_with_db() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    """FastAPI TestClient with isolated SQLite database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test_clips.db"
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


def test_clip_crud_full_lifecycle(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """Test full CRUD operations for video clip segments."""
    client, session_factory = client_with_db
    db = session_factory()
    video = Video(
        path="/media/crud_test.mp4",
        filename="crud_test.mp4",
        size=50000,
        duration=100.0,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    vid = video.id
    db.close()

    # 1. Create clip segment
    create_res = client.post(
        f"/api/videos/{vid}/clips",
        json={
            "start_seconds": 10.5,
            "end_seconds": 25.0,
            "label": "Opening Scene",
            "note": "Camera pan",
            "order_index": 1,
        },
    )
    assert create_res.status_code == 201
    clip_data = create_res.json()
    clip_id = clip_data["id"]
    assert clip_data["video_id"] == vid
    assert clip_data["start_seconds"] == 10.5
    assert clip_data["end_seconds"] == 25.0
    assert clip_data["label"] == "Opening Scene"
    assert clip_data["note"] == "Camera pan"
    assert clip_data["order_index"] == 1
    assert clip_data["order"] == 1
    assert "created_at" in clip_data
    assert "updated_at" in clip_data

    # 2. Get single clip by ID
    get_res = client.get(f"/api/videos/{vid}/clips/{clip_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == clip_id
    assert get_res.json()["label"] == "Opening Scene"

    # 3. List clips for video
    list_res = client.get(f"/api/videos/{vid}/clips")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) == 1
    assert items[0]["id"] == clip_id

    # Also test via /api/catalog route alias
    catalog_list = client.get(f"/api/catalog/{vid}/clips")
    assert catalog_list.status_code == 200
    assert len(catalog_list.json()) == 1

    # 4. Update clip segment (PUT)
    update_res = client.put(
        f"/api/videos/{vid}/clips/{clip_id}",
        json={
            "start_seconds": 12.0,
            "end_seconds": 30.0,
            "label": "Updated Scene",
            "note": "Updated note",
            "order_index": 2,
        },
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["start_seconds"] == 12.0
    assert updated_data["end_seconds"] == 30.0
    assert updated_data["label"] == "Updated Scene"
    assert updated_data["note"] == "Updated note"
    assert updated_data["order_index"] == 2

    # 5. Partial update via PATCH
    patch_res = client.patch(
        f"/api/videos/{vid}/clips/{clip_id}",
        json={"label": "Patched Scene"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["label"] == "Patched Scene"
    assert patch_res.json()["start_seconds"] == 12.0

    # 6. Delete clip segment
    del_res = client.delete(f"/api/videos/{vid}/clips/{clip_id}")
    assert del_res.status_code == 204

    # Verify deleted
    get_after_del = client.get(f"/api/videos/{vid}/clips/{clip_id}")
    assert get_after_del.status_code == 404

    list_after_del = client.get(f"/api/videos/{vid}/clips")
    assert list_after_del.status_code == 200
    assert len(list_after_del.json()) == 0


def test_clip_ordering_multiple_segments(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """Test that multiple clip segments are returned in proper sequential order."""
    client, session_factory = client_with_db
    db = session_factory()
    video = Video(
        path="/media/order_test.mp4",
        filename="order_test.mp4",
        size=10000,
        duration=200.0,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    vid = video.id
    db.close()

    # Create 3 clips out of order chronologically and with order_index
    # Clip A: order 3, start 80
    res_a = client.post(
        f"/api/videos/{vid}/clips",
        json={"start_seconds": 80.0, "end_seconds": 90.0, "label": "Part 3", "order_index": 3},
    )
    assert res_a.status_code == 201

    # Clip B: order 1, start 10
    res_b = client.post(
        f"/api/videos/{vid}/clips",
        json={"start_seconds": 10.0, "end_seconds": 20.0, "label": "Part 1", "order_index": 1},
    )
    assert res_b.status_code == 201

    # Clip C: order 2, start 40
    res_c = client.post(
        f"/api/videos/{vid}/clips",
        json={"start_seconds": 40.0, "end_seconds": 50.0, "label": "Part 2", "order_index": 2},
    )
    assert res_c.status_code == 201

    # List clips: should be Part 1 -> Part 2 -> Part 3
    list_res = client.get(f"/api/videos/{vid}/clips")
    assert list_res.status_code == 200
    clips = list_res.json()
    assert len(clips) == 3
    assert [c["label"] for c in clips] == ["Part 1", "Part 2", "Part 3"]

    # When order_index is identical (e.g. 0), clips should sort by start_seconds
    db2 = session_factory()
    video2 = Video(
        path="/media/order_chronological.mp4",
        filename="order_chronological.mp4",
        size=10000,
        duration=100.0,
    )
    db2.add(video2)
    db2.commit()
    db2.refresh(video2)
    vid2 = video2.id
    db2.close()

    client.post(
        f"/api/videos/{vid2}/clips",
        json={"start_seconds": 50.0, "end_seconds": 60.0, "label": "Later"},
    )
    client.post(
        f"/api/videos/{vid2}/clips",
        json={"start_seconds": 5.0, "end_seconds": 15.0, "label": "Earlier"},
    )

    list2 = client.get(f"/api/videos/{vid2}/clips").json()
    assert len(list2) == 2
    assert list2[0]["label"] == "Earlier"
    assert list2[1]["label"] == "Later"


def test_clip_validation_rules(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """Test start/end validations: finite nonnegative, end > start, end <= duration."""
    client, session_factory = client_with_db
    db = session_factory()
    video = Video(
        path="/media/validation_test.mp4",
        filename="validation_test.mp4",
        size=10000,
        duration=60.0,  # 60s total duration
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    vid = video.id
    db.close()

    # Negative start_seconds -> rejected
    r1 = client.post(
        f"/api/videos/{vid}/clips",
        json={"start_seconds": -5.0, "end_seconds": 10.0},
    )
    assert r1.status_code in (400, 422)

    # end_seconds equal to start_seconds -> rejected
    r2 = client.post(
        f"/api/videos/{vid}/clips",
        json={"start_seconds": 10.0, "end_seconds": 10.0},
    )
    assert r2.status_code in (400, 422)

    # end_seconds less than start_seconds -> rejected
    r3 = client.post(
        f"/api/videos/{vid}/clips",
        json={"start_seconds": 20.0, "end_seconds": 10.0},
    )
    assert r3.status_code in (400, 422)

    # end_seconds exceeds video duration (60.0s) -> 400 Bad Request
    r4 = client.post(
        f"/api/videos/{vid}/clips",
        json={"start_seconds": 10.0, "end_seconds": 60.1},
    )
    assert r4.status_code == 400
    assert "exceeds video duration" in r4.json()["detail"]

    # end_seconds exactly equals duration -> accepted
    r5 = client.post(
        f"/api/videos/{vid}/clips",
        json={"start_seconds": 0.0, "end_seconds": 60.0},
    )
    assert r5.status_code == 201
    clip_id = r5.json()["id"]

    # Updating with end_seconds > duration -> rejected
    r6 = client.put(
        f"/api/videos/{vid}/clips/{clip_id}",
        json={"end_seconds": 65.0},
    )
    assert r6.status_code in (400, 422)

    # Video with duration = None -> end_seconds can exceed normal sizes without 400
    db2 = session_factory()
    no_dur_vid = Video(
        path="/media/unknown_dur.mp4",
        filename="unknown_dur.mp4",
        size=10000,
        duration=None,
    )
    db2.add(no_dur_vid)
    db2.commit()
    db2.refresh(no_dur_vid)
    v2_id = no_dur_vid.id
    db2.close()

    r7 = client.post(
        f"/api/videos/{v2_id}/clips",
        json={"start_seconds": 100.0, "end_seconds": 99999.0},
    )
    assert r7.status_code == 201


def test_missing_videos_error_handling(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """Test proper 404 responses for missing videos across clip and decision APIs."""
    client, session_factory = client_with_db
    missing_id = 999999

    # Clips endpoints
    assert client.get(f"/api/videos/{missing_id}/clips").status_code == 404
    assert (
        client.post(
            f"/api/videos/{missing_id}/clips",
            json={"start_seconds": 0.0, "end_seconds": 10.0},
        ).status_code
        == 404
    )
    assert client.get(f"/api/videos/{missing_id}/clips/1").status_code == 404
    assert (
        client.put(
            f"/api/videos/{missing_id}/clips/1",
            json={"start_seconds": 1.0, "end_seconds": 5.0},
        ).status_code
        == 404
    )
    assert client.delete(f"/api/videos/{missing_id}/clips/1").status_code == 404

    # Decision endpoint
    assert (
        client.post(
            f"/api/videos/{missing_id}/decision",
            json={"decision": "no_action"},
        ).status_code
        == 404
    )

    # Cross-video access: clip belonging to video A accessed with video B
    db = session_factory()
    v1 = Video(path="/media/v1.mp4", filename="v1.mp4", size=100, duration=50.0)
    v2 = Video(path="/media/v2.mp4", filename="v2.mp4", size=100, duration=50.0)
    db.add_all([v1, v2])
    db.commit()
    db.refresh(v1)
    db.refresh(v2)

    clip = ClipSegment(video_id=v1.id, start_seconds=1.0, end_seconds=5.0)
    db.add(clip)
    db.commit()
    db.refresh(clip)
    c_id = clip.id
    v2_id = v2.id
    db.close()

    # Attempt to access v1's clip via v2 URL -> 404
    assert client.get(f"/api/videos/{v2_id}/clips/{c_id}").status_code == 404
    assert (
        client.put(
            f"/api/videos/{v2_id}/clips/{c_id}",
            json={"start_seconds": 2.0, "end_seconds": 6.0},
        ).status_code
        == 404
    )
    assert client.delete(f"/api/videos/{v2_id}/clips/{c_id}").status_code == 404


def test_decision_no_action_vs_clip_selected(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """Test explicit decision endpoint constraints for no_action vs clip_selected."""
    client, session_factory = client_with_db
    db = session_factory()
    video = Video(
        path="/media/decision_test.mp4",
        filename="decision_test.mp4",
        size=10000,
        duration=120.0,
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    vid = video.id
    db.close()

    # 1. Video has 0 segments: clip_selected MUST FAIL (requires at least 1)
    res_invalid_clip = client.post(
        f"/api/videos/{vid}/decision",
        json={"decision": "clip_selected"},
    )
    assert res_invalid_clip.status_code == 400
    assert "0 clip segments" in res_invalid_clip.json()["detail"]

    # 2. Video has 0 segments: no_action MUST SUCCEED
    res_no_action = client.post(
        f"/api/videos/{vid}/decision",
        json={"decision": "no_action"},
    )
    assert res_no_action.status_code == 200
    assert res_no_action.json()["status"] == "no_action"
    assert res_no_action.json()["decision"] == "no_action"

    # Also check video in catalog has status no_action
    cat_video = client.get(f"/api/videos/{vid}").json()
    assert cat_video["status"] == "no_action"

    # 3. Add a clip segment to video
    add_clip = client.post(
        f"/api/videos/{vid}/clips",
        json={"start_seconds": 5.0, "end_seconds": 15.0, "label": "Key segment"},
    )
    assert add_clip.status_code == 201

    # 4. Now video has 1 segment: no_action MUST FAIL (requires 0 segments)
    res_invalid_no_action = client.post(
        f"/api/videos/{vid}/decision",
        json={"decision": "no_action"},
    )
    assert res_invalid_no_action.status_code == 400
    assert "existing clip segment(s)" in res_invalid_no_action.json()["detail"]

    # 5. With 1 segment: clip_selected MUST SUCCEED (using 'status' payload alias)
    res_clip_selected = client.post(
        f"/api/videos/{vid}/decision",
        json={"status": "clip_selected"},
    )
    assert res_clip_selected.status_code == 200
    assert res_clip_selected.json()["status"] == "clip_selected"

    # 6. Unsupported / invalid decision type -> 422
    res_unsupported = client.post(
        f"/api/videos/{vid}/decision",
        json={"decision": "discarded"},
    )
    assert res_unsupported.status_code == 422


def test_repeated_decisions_and_idempotency(
    client_with_db: tuple[TestClient, sessionmaker[Session]],
) -> None:
    """Test idempotent decision updates and audit timestamp preservation."""
    client, session_factory = client_with_db
    db = session_factory()
    video = Video(
        path="/media/idempotent_test.mp4",
        filename="idempotent_test.mp4",
        size=10000,
        duration=50.0,
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    vid = video.id
    original_created_at = video.created_at
    db.close()

    # Call no_action first time
    res1 = client.post(f"/api/videos/{vid}/decision", json={"decision": "no_action"})
    assert res1.status_code == 200
    assert res1.json()["status"] == "no_action"
    assert "updated_at" in res1.json()

    # Call no_action second time (idempotent repeated call)
    res2 = client.post(f"/api/videos/{vid}/decision", json={"decision": "no_action"})
    assert res2.status_code == 200
    assert res2.json()["status"] == "no_action"

    # Verify created_at remains unchanged
    v_record = client.get(f"/api/videos/{vid}").json()
    assert datetime.fromisoformat(v_record["created_at"]) == original_created_at
    assert v_record["status"] == "no_action"

    # Add clip and call clip_selected multiple times
    client.post(
        f"/api/videos/{vid}/clips",
        json={"start_seconds": 1.0, "end_seconds": 10.0},
    )

    res3 = client.post(f"/api/videos/{vid}/decision", json={"decision": "clip_selected"})
    assert res3.status_code == 200
    assert res3.json()["status"] == "clip_selected"

    res4 = client.post(f"/api/videos/{vid}/decision", json={"decision": "clip_selected"})
    assert res4.status_code == 200
    assert res4.json()["status"] == "clip_selected"
