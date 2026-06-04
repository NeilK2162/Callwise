"""Async ingest/job status (PRD §11.1)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from callwise.control_api.deps import CurrentUser, DbSession, owned_or_404
from callwise.control_api.schemas import JobOut
from callwise.db.models import IngestJob

router = APIRouter()


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, db: DbSession, user: CurrentUser) -> IngestJob:
    job = await db.get(IngestJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    owned_or_404(job.owner_id, user)
    return job
