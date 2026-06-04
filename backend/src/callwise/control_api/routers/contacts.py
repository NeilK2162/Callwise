"""Contacts + ingest (PRD §5.1, §11.1).

Upload creates a campaign + an async ingest job. Large files (>50k rows) are processed in
a worker with streaming parse + chunked COPY, progress over WebSocket; the request returns
a `job_id` immediately so the API pod never OOMs on a 5M-row file (edge case #21).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from callwise.control_api.deps import CurrentUser, DbSession
from callwise.control_api.schemas import ContactOut, UploadResponse
from callwise.db.models import Campaign, Contact, IngestJob
from callwise.logging import get_logger

router = APIRouter()
log = get_logger(__name__)

_TEMPLATE = "phone,customer_name,language,timezone,custom_field_1,custom_field_2\n"


@router.get("/template", response_class=PlainTextResponse)
async def template() -> str:
    return _TEMPLATE


@router.post("/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile,
    db: DbSession,
    user: CurrentUser,
    campaign_name: str = Query(default="Imported campaign"),
) -> UploadResponse:
    campaign = Campaign(owner_id=user.id, name=campaign_name, provider="mock")
    db.add(campaign)
    await db.flush()
    job = IngestJob(campaign_id=campaign.id, owner_id=user.id, status="pending")
    db.add(job)
    await db.commit()
    # TODO: stream file -> S3, enqueue `ingest_file` task; worker does the chunked import,
    #       E.164 normalization, in-file dedup, and a downloadable rejected_rows artifact.
    log.info("ingest_job_created", job_id=str(job.id), filename=file.filename)
    return UploadResponse(job_id=job.id, campaign_id=campaign.id, status=job.status)


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    campaign_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(default=100, le=1000),
) -> list[Contact]:
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None or (not user.is_superuser and campaign.owner_id != user.id):
        return []
    stmt = (
        select(Contact)
        .where(Contact.campaign_id == campaign_id)
        .order_by(Contact.created_at.desc())
        .limit(limit)
    )
    return list(await db.scalars(stmt))
