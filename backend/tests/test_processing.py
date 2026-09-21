"""Focused temporary-directory tests for video clip processing and archive replacement.

Validates:
- Job lifecycle transitions (queued -> running -> succeeded / failed / cancelled)
- Idempotency protection rejecting duplicate active jobs
- Source path validation, video roots containment, and destination root checks
- Rejection of videos already replaced, discarded, or lacking clip segments
- FFmpeg command construction with stream-copy concat preference and re-encode fallback
- Temporary output generation within original directory and non-empty validation
- Deterministic collision-safe movement of original to ARCHIVE_DIR (original never deleted)
- Atomic replacement of original file path with rendered output
- Video status updated to 'replaced' only after full filesystem and DB success
- Rollback and original preservation upon failures at:
  * Render step
  * Output validation step (empty file)
  * Archive move step
  * Atomic replace step
  * Database commit step
- REST API endpoints for processing jobs (/api/videos/{id}/process, /jobs, /cancel)
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app
from app.models.clip import ClipSegment
from app.models.job import JobStatus
from app.models.video import Video, VideoStatus
from app.services.ffmpeg_runner import MockFFmpegRunner
from app.services.processing import ProcessingService, processing_service


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


def create_sample_video_with_clips(
    db: Session,
    source_file: Path,
    status: str = VideoStatus.UNPROCESSED.value,
    duration: float = 60.0,
    clip_ranges: list[tuple[float, float]] | None = None,
) -> Video:
    """Helper to insert a video with ordered clip segments."""
    source_file.parent.mkdir(parents=True, exist_ok=True)
    if not source_file.exists():
        source_file.write_bytes(b"ORIGINAL_VIDEO_CONTENT_123456789")

    video = Video(
        path=str(source_file.resolve()),
        filename=source_file.name,
        size=source_file.stat().st_size,
        duration=duration,
        status=status,
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    ranges = clip_ranges if clip_ranges is not None else [(2.0, 10.0), (15.0, 25.0)]
    for idx, (start, end) in enumerate(ranges):
        clip = ClipSegment(
            video_id=video.id,
            start_seconds=start,
            end_seconds=end,
            order_index=idx,
        )
        db.add(clip)

    db.commit()
    db.refresh(video)
    return video


def test_job_idempotency_duplicate_active_rejected(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test idempotency: reject duplicate active jobs for the same video with 409 Conflict."""
    client, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    db = session_factory()
    video_file = video_root / "test_idem.mp4"
    video = create_sample_video_with_clips(db, video_file)
    video_id = video.id

    svc = ProcessingService(
        runner=MockFFmpegRunner(succeed=True),
        archive_dir=archive_root,
        video_roots=[str(video_root)],
    )

    # 1. Create first job -> QUEUED
    job1 = svc.create_job(db=db, video_id=video_id)
    assert job1.status == JobStatus.QUEUED.value

    # 2. Attempt duplicate while job1 is QUEUED -> HTTP 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        svc.create_job(db=db, video_id=video_id)
    assert "409" in str(exc_info.value) or exc_info.value.status_code == 409

    # 3. Transition job1 to RUNNING -> duplicate still rejected
    job1.status = JobStatus.RUNNING.value
    db.commit()
    with pytest.raises(HTTPException) as exc_info2:
        svc.create_job(db=db, video_id=video_id)
    assert "409" in str(exc_info2.value) or exc_info2.value.status_code == 409

    # 4. Once job1 finishes (FAILED or SUCCEEDED), a new job can be enqueued
    job1.status = JobStatus.FAILED.value
    db.commit()
    job2 = svc.create_job(db=db, video_id=video_id)
    assert job2.id != job1.id
    assert job2.status == JobStatus.QUEUED.value
    db.close()


def test_job_cancellation(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test cancellation of queued processing job."""
    _, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    db = session_factory()
    video = create_sample_video_with_clips(db, video_root / "test_cancel.mp4")

    svc = ProcessingService(
        runner=MockFFmpegRunner(succeed=True),
        archive_dir=archive_root,
        video_roots=[str(video_root)],
    )

    job = svc.create_job(db=db, video_id=video.id)
    assert job.status == JobStatus.QUEUED.value

    cancelled = svc.cancel_job(db=db, job_id=job.id)
    assert cancelled.status == JobStatus.CANCELLED.value
    assert cancelled.completed_at is not None

    # Cannot cancel already cancelled job
    with pytest.raises(Exception) as exc:
        svc.cancel_job(db=db, job_id=job.id)
    assert "cannot be cancelled" in str(exc.value)
    db.close()


def test_validation_rejected_conditions(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test validation errors for missing video, already replaced, no clips, and escapes."""
    _, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    db = session_factory()
    svc = ProcessingService(archive_dir=archive_root, video_roots=[str(video_root)])

    # 1. Non-existent video ID
    with pytest.raises(Exception) as exc1:
        svc.create_job(db=db, video_id=99999)
    assert "not found" in str(exc1.value).lower()

    # 2. Already replaced video
    v_replaced = create_sample_video_with_clips(
        db, video_root / "already_rep.mp4", status=VideoStatus.REPLACED.value
    )
    with pytest.raises(Exception) as exc2:
        svc.create_job(db=db, video_id=v_replaced.id)
    assert "already replaced" in str(exc2.value).lower()

    # 3. Discarded video
    v_discarded = create_sample_video_with_clips(
        db, video_root / "already_disc.mp4", status=VideoStatus.DISCARDED.value
    )
    with pytest.raises(Exception) as exc3:
        svc.create_job(db=db, video_id=v_discarded.id)
    assert "discarded" in str(exc3.value).lower()

    # 4. Video without clip segments
    v_no_clips = create_sample_video_with_clips(
        db, video_root / "no_clips.mp4", clip_ranges=[]
    )
    with pytest.raises(Exception) as exc4:
        svc.create_job(db=db, video_id=v_no_clips.id)
    assert "no clip segments" in str(exc4.value).lower()

    # 5. Missing source file on disk
    v_missing_file = create_sample_video_with_clips(
        db, video_root / "missing_on_disk.mp4"
    )
    Path(v_missing_file.path).unlink(missing_ok=True)
    with pytest.raises(Exception) as exc5:
        svc.create_job(db=db, video_id=v_missing_file.id)
    assert "not found on disk" in str(exc5.value).lower()

    # 6. Source file outside configured roots (path traversal / escape)
    other_root = tmp_path / "outside"
    other_root.mkdir(parents=True)
    outside_file = other_root / "outside.mp4"
    outside_file.write_bytes(b"DATA")
    v_outside = Video(
        path=str(outside_file.resolve()),
        filename="outside.mp4",
        size=4,
        status=VideoStatus.UNPROCESSED.value,
    )
    db.add(v_outside)
    db.commit()
    db.refresh(v_outside)
    db.add(ClipSegment(video_id=v_outside.id, start_seconds=0, end_seconds=1))
    db.commit()

    with pytest.raises(Exception) as exc6:
        svc.create_job(db=db, video_id=v_outside.id)
    assert "outside configured video roots" in str(exc6.value).lower()

    db.close()


def test_successful_archive_and_replace_stream_copy(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test full successful workflow: render, validate temp, archive original,
    atomically replace.
    """
    _, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    db = session_factory()
    orig_bytes = b"ORIGINAL_HIGH_QUALITY_VIDEO_DATA"
    rendered_bytes = b"RENDERED_CONCATENATED_CLIPS_DATA"

    source_file = video_root / "feature.mp4"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(orig_bytes)

    video = create_sample_video_with_clips(db, source_file)
    video_id = video.id

    mock_runner = MockFFmpegRunner(succeed=True, dummy_content=rendered_bytes)
    svc = ProcessingService(
        runner=mock_runner,
        archive_dir=archive_root,
        video_roots=[str(video_root)],
    )

    job = svc.create_job(db=db, video_id=video_id)
    assert job.status == JobStatus.QUEUED.value

    # Run the job synchronously
    finished_job = svc.run_job(job_id=job.id, db=db)

    assert finished_job.status == JobStatus.SUCCEEDED.value
    assert finished_job.strategy == "stream_copy"
    assert finished_job.progress == 1.0

    # Verify original file was preserved in ARCHIVE_DIR and never deleted
    expected_archived = archive_root / "feature.mp4"
    assert expected_archived.exists(), "Original video must be archived, never deleted"
    assert expected_archived.read_bytes() == orig_bytes

    # Verify original path exists and now contains rendered content
    assert source_file.exists()
    assert source_file.read_bytes() == rendered_bytes

    # Verify Video record updated to 'replaced'
    db.refresh(video)
    assert video.status == VideoStatus.REPLACED.value
    assert video.size == len(rendered_bytes)
    assert video.move_metadata is not None
    assert video.move_metadata["archived_to"] == str(expected_archived)

    # Verify no leftover temporary files in video_root
    temp_files = list(video_root.glob(".processing_tmp_*"))
    assert len(temp_files) == 0

    db.close()


def test_successful_archive_and_replace_reencode_fallback(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test successful archive and replace when falling back to H.264/AAC re-encode."""
    _, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    db = session_factory()
    orig_bytes = b"ORIGINAL_VIDEO_NEEDING_REENCODE"
    rendered_bytes = b"REENCODED_CLIPS_DATA"

    source_file = video_root / "camera.mp4"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(orig_bytes)

    video = create_sample_video_with_clips(db, source_file)

    # Fail stream-copy so pipeline falls back to re-encode
    mock_runner = MockFFmpegRunner(
        succeed=True, fail_stream_copy=True, dummy_content=rendered_bytes
    )
    svc = ProcessingService(
        runner=mock_runner,
        archive_dir=archive_root,
        video_roots=[str(video_root)],
    )

    job = svc.create_job(db=db, video_id=video.id)
    finished_job = svc.run_job(job_id=job.id, db=db)

    assert finished_job.status == JobStatus.SUCCEEDED.value
    assert finished_job.strategy == "reencode"

    # Original archived and replaced
    assert (archive_root / "camera.mp4").read_bytes() == orig_bytes
    assert source_file.read_bytes() == rendered_bytes

    db.refresh(video)
    assert video.status == VideoStatus.REPLACED.value
    db.close()


def test_archive_collision_avoidance(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test deterministic collision avoidance when destination file already
    exists in ARCHIVE_DIR.
    """
    _, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    # Pre-populate archive with collision candidate
    existing_archive = archive_root / "clip_video.mp4"
    existing_archive.write_bytes(b"PRE_EXISTING_ARCHIVE_FILE")

    db = session_factory()
    source_file = video_root / "clip_video.mp4"
    orig_bytes = b"CURRENT_ORIGINAL_FILE_CONTENT"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(orig_bytes)

    video = create_sample_video_with_clips(db, source_file)

    svc = ProcessingService(
        runner=MockFFmpegRunner(succeed=True, dummy_content=b"NEW_RENDERED"),
        archive_dir=archive_root,
        video_roots=[str(video_root)],
    )

    job = svc.create_job(db=db, video_id=video.id)
    finished_job = svc.run_job(job_id=job.id, db=db)

    assert finished_job.status == JobStatus.SUCCEEDED.value

    # Pre-existing archive must NOT be overwritten
    assert existing_archive.read_bytes() == b"PRE_EXISTING_ARCHIVE_FILE"

    # Original must be moved to deterministic collision-free name
    expected_new_archive = archive_root / "clip_video_1.mp4"
    assert expected_new_archive.exists()
    assert expected_new_archive.read_bytes() == orig_bytes
    assert finished_job.archive_path == str(expected_new_archive)

    db.close()


def test_failure_at_render_step_rollback(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test failure during render step preserves original file and DB status, cleans temp file."""
    _, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    db = session_factory()
    orig_bytes = b"ORIGINAL_MUST_BE_SAVED"
    source_file = video_root / "render_fail.mp4"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(orig_bytes)

    video = create_sample_video_with_clips(db, source_file, status=VideoStatus.CLIP_SELECTED.value)

    mock_runner = MockFFmpegRunner(succeed=False, error_message="FFmpeg process segfaulted")
    svc = ProcessingService(
        runner=mock_runner,
        archive_dir=archive_root,
        video_roots=[str(video_root)],
    )

    job = svc.create_job(db=db, video_id=video.id)

    with pytest.raises(RuntimeError, match="segfaulted"):
        svc.run_job(job_id=job.id, db=db)

    # Verify job marked failed with error
    db.refresh(job)
    assert job.status == JobStatus.FAILED.value
    assert "segfaulted" in str(job.error)

    # Verify original file untouched
    assert source_file.exists()
    assert source_file.read_bytes() == orig_bytes

    # Verify Video status unchanged
    db.refresh(video)
    assert video.status == VideoStatus.CLIP_SELECTED.value

    # Verify temp files cleaned up
    assert len(list(video_root.glob(".processing_tmp_*"))) == 0

    db.close()


def test_failure_at_temp_validation_step_rollback(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that 0-byte or missing temp output fails validation and preserves original."""
    _, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    db = session_factory()
    orig_bytes = b"ORIGINAL_MUST_BE_SAVED"
    source_file = video_root / "empty_output.mp4"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(orig_bytes)

    video = create_sample_video_with_clips(db, source_file, status=VideoStatus.UNPROCESSED.value)

    # Mock runner outputs 0 bytes (empty file)
    mock_runner = MockFFmpegRunner(succeed=True, dummy_content=b"")
    svc = ProcessingService(
        runner=mock_runner,
        archive_dir=archive_root,
        video_roots=[str(video_root)],
    )

    job = svc.create_job(db=db, video_id=video.id)

    with pytest.raises(RuntimeError, match="empty"):
        svc.run_job(job_id=job.id, db=db)

    db.refresh(job)
    assert job.status == JobStatus.FAILED.value
    assert source_file.exists()
    assert source_file.read_bytes() == orig_bytes

    db.refresh(video)
    assert video.status == VideoStatus.UNPROCESSED.value

    db.close()


def test_failure_at_archive_step_rollback(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test failure during archive move restores original and cleans temp file."""
    _, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    db = session_factory()
    orig_bytes = b"ORIGINAL_MUST_BE_SAVED"
    source_file = video_root / "archive_fail.mp4"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(orig_bytes)

    video = create_sample_video_with_clips(db, source_file)

    svc = ProcessingService(
        runner=MockFFmpegRunner(succeed=True, dummy_content=b"RENDERED"),
        archive_dir=archive_root,
        video_roots=[str(video_root)],
    )

    job = svc.create_job(db=db, video_id=video.id)

    # Simulate filesystem failure during move_file_safely
    with patch("app.services.processing.move_file_safely", side_effect=OSError("Disk write error")):
        with pytest.raises(OSError, match="Disk write error"):
            svc.run_job(job_id=job.id, db=db)

    db.refresh(job)
    assert job.status == JobStatus.FAILED.value
    assert source_file.exists()
    assert source_file.read_bytes() == orig_bytes

    db.refresh(video)
    assert video.status == VideoStatus.UNPROCESSED.value
    assert len(list(video_root.glob(".processing_tmp_*"))) == 0

    db.close()


def test_failure_at_replace_step_rollback(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test failure during atomic os.replace restores original from archive."""
    _, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    db = session_factory()
    orig_bytes = b"ORIGINAL_NEEDS_RESTORATION"
    source_file = video_root / "replace_fail.mp4"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(orig_bytes)

    video = create_sample_video_with_clips(db, source_file)

    svc = ProcessingService(
        runner=MockFFmpegRunner(succeed=True, dummy_content=b"RENDERED"),
        archive_dir=archive_root,
        video_roots=[str(video_root)],
    )

    job = svc.create_job(db=db, video_id=video.id)

    # Patch os.replace to fail only during the atomic replace call
    real_replace = os.replace

    def selective_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        if ".processing_tmp_" in str(src):
            raise OSError("Access denied replacing original file")
        real_replace(src, dst)

    with patch("os.replace", side_effect=selective_replace):
        with pytest.raises(RuntimeError, match="Atomic replacement of original path failed"):
            svc.run_job(job_id=job.id, db=db)

    db.refresh(job)
    assert job.status == JobStatus.FAILED.value

    # Original should be safely restored at source_file
    assert source_file.exists()
    assert source_file.read_bytes() == orig_bytes

    db.refresh(video)
    assert video.status == VideoStatus.UNPROCESSED.value

    db.close()


def test_failure_at_db_commit_step_rollback(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test failure at database commit restores original file from archive."""
    _, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    db = session_factory()
    orig_bytes = b"ORIGINAL_MUST_BE_RESTORED_ON_DB_FAIL"
    source_file = video_root / "db_fail.mp4"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(orig_bytes)

    video = create_sample_video_with_clips(db, source_file)

    svc = ProcessingService(
        runner=MockFFmpegRunner(succeed=True, dummy_content=b"RENDERED"),
        archive_dir=archive_root,
        video_roots=[str(video_root)],
    )

    job = svc.create_job(db=db, video_id=video.id)

    # Mock session.commit to fail on the final update step
    real_commit = db.commit
    commit_count = 0

    def fail_on_final_commit() -> None:
        nonlocal commit_count
        commit_count += 1
        # Fail when updating video.status to replaced (which is the 5th commit)
        if commit_count >= 5:
            raise RuntimeError("Database locked / disk I/O error")
        real_commit()

    with patch.object(db, "commit", side_effect=fail_on_final_commit):
        with pytest.raises(RuntimeError, match="Database commit failed after replacement"):
            svc.run_job(job_id=job.id, db=db)

    # Original video file must be restored back
    assert source_file.exists()
    assert source_file.read_bytes() == orig_bytes

    # Video status must not be replaced
    db.refresh(video)
    assert video.status != VideoStatus.REPLACED.value

    db.close()


def test_api_process_and_jobs_endpoints(
    tmp_path: Path,
    client_with_db: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test processing REST API endpoints via TestClient."""
    client, session_factory = client_with_db
    video_root = tmp_path / "videos"
    archive_root = tmp_path / "archive"
    monkeypatch.setattr(settings, "video_roots", [str(video_root)])
    monkeypatch.setattr(settings, "archive_dir", archive_root)

    # Inject mock runner into global processing_service
    mock_runner = MockFFmpegRunner(succeed=True, dummy_content=b"API_RENDERED")
    monkeypatch.setattr(processing_service, "runner", mock_runner)
    monkeypatch.setattr(processing_service, "_custom_archive_dir", archive_root)
    monkeypatch.setattr(processing_service, "_custom_video_roots", [str(video_root)])

    db = session_factory()
    source_file = video_root / "api_video.mp4"
    video = create_sample_video_with_clips(db, source_file)
    video_id = video.id
    db.close()

    # 1. Trigger process via API
    resp = client.post(f"/api/videos/{video_id}/process?background=false")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "succeeded"
    assert data["video_id"] == video_id
    assert data["progress"] == 1.0
    job_id = data["id"]

    # 2. Query job list for video
    resp_list = client.get(f"/api/videos/{video_id}/jobs")
    assert resp_list.status_code == 200
    jobs_list = resp_list.json()
    assert len(jobs_list) == 1
    assert jobs_list[0]["id"] == job_id

    # 3. Query latest job for video
    resp_latest = client.get(f"/api/videos/{video_id}/jobs/latest")
    assert resp_latest.status_code == 200
    assert resp_latest.json()["id"] == job_id

    # 4. Query job directly via /api/jobs/{job_id}
    resp_direct = client.get(f"/api/jobs/{job_id}")
    assert resp_direct.status_code == 200
    assert resp_direct.json()["id"] == job_id

    # 5. Verify video was marked replaced
    resp_video = client.get(f"/api/videos/{video_id}")
    assert resp_video.status_code == 200
    assert resp_video.json()["status"] == "replaced"
