"""Direct processing jobs API router module.

Provides global endpoints to query and cancel processing jobs by job ID.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.job import ProcessingJobRead
from app.services.processing import processing_service

router = APIRouter()


@router.get(
    "/{job_id}",
    response_model=ProcessingJobRead,
    summary="Get processing job by ID",
)
def get_job_by_id(
    job_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> ProcessingJobRead:
    """Retrieve details and progress of a processing job."""
    job = processing_service.get_job(db=db, job_id=job_id)
    return ProcessingJobRead.model_validate(job)


@router.post(
    "/{job_id}/cancel",
    response_model=ProcessingJobRead,
    summary="Cancel processing job by ID",
)
def cancel_job_by_id(
    job_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> ProcessingJobRead:
    """Cancel a pending or running processing job."""
    job = processing_service.cancel_job(db=db, job_id=job_id)
    return ProcessingJobRead.model_validate(job)
