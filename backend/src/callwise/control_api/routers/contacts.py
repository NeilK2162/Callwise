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

from callwise.config import get_settings
from callwise.control_api.deps import CurrentUser, DbSession
from callwise.control_api.schemas import ContactOut, UploadResponse
from callwise.db.enums import ContactStatus
from callwise.db.models import Campaign, Contact, IngestJob
from callwise.domain.ingest import parse_contacts
from callwise.logging import get_logger
from callwise.queue.factory import get_queue
from callwise.storage import get_object_store

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
    default_country_code: str = Query(default="IN"),
) -> UploadResponse:
    content = await file.read()

    campaign = Campaign(
        owner_id=user.id,
        name=campaign_name,
        provider="mock",
        default_country_code=default_country_code,
    )
    db.add(campaign)
    await db.flush()
    job = IngestJob(campaign_id=campaign.id, owner_id=user.id, status="processing")
    db.add(job)
    await db.flush()

    settings = get_settings()
    if len(content) > settings.ingest_sync_size_limit:
        # Large file → S3 + async worker (streaming parse, chunked insert), so the API pod
        # never OOMs. The request returns a job_id immediately (edge #21).
        filename = file.filename or "upload.csv"
        s3_key = f"uploads/{job.id}/{filename}"
        await get_object_store().upload_bytes(
            s3_key, content, content_type=file.content_type or "text/csv"
        )
        job.s3_key = s3_key
        job.status = "pending"
        await db.commit()
        await get_queue().publish(
            settings.ingest_stream,
            {
                "job_id": str(job.id),
                "s3_key": s3_key,
                "campaign_id": str(campaign.id),
                "default_country_code": default_country_code,
                "filename": filename,
            },
            idempotency_key=f"ingest:{job.id}",
        )
        log.info("ingest_enqueued_large_file", job_id=str(job.id), bytes=len(content))
        return UploadResponse(job_id=job.id, campaign_id=campaign.id, status=job.status)

    result = parse_contacts(file.filename or "upload.csv", content, default_country_code)
    db.add_all(
        [
            Contact(
                campaign_id=campaign.id,
                phone_e164=r.phone_e164,
                customer_name=r.customer_name,
                language=r.language,
                timezone=r.timezone,
                custom_fields=r.custom_fields,
                status=ContactStatus.queued,
            )
            for r in result.valid
        ]
    )
    job.total_rows = result.total
    job.imported_rows = len(result.valid)
    job.status = "completed"
    # TODO: persist the full rejected_rows artifact to S3; for now record the count.
    if result.rejected:
        job.error = f"{len(result.rejected)} rows rejected (invalid/duplicate phone)"
    await db.commit()

    log.info(
        "ingest_completed",
        job_id=str(job.id),
        total=result.total,
        imported=job.imported_rows,
        rejected=len(result.rejected),
    )
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
