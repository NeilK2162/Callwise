"""Async large-file ingest worker (PRD §5.1, edge #21).

Large uploads are written to S3 by the API and a job is enqueued here. This worker
downloads the file, streaming-parses it, bulk-inserts contacts in chunks of 5,000,
collects a downloadable `rejected_rows` artifact, and reports progress on the IngestJob —
so a 5M-row file never OOMs the API pod.
"""

from __future__ import annotations

import csv
import io
import uuid

from callwise.config import get_settings
from callwise.db.base import get_sessionmaker
from callwise.db.enums import ContactStatus
from callwise.db.models import Contact, IngestJob
from callwise.domain.ingest import parse_contacts
from callwise.logging import bind_call_context, get_logger
from callwise.queue.base import Message
from callwise.storage import get_object_store
from callwise.workers.base import StreamWorker, run_worker

log = get_logger(__name__)

_BATCH = 5000


def _rejected_csv(rejected: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["reason", "row"])
    for item in rejected:
        writer.writerow([item.get("reason", ""), str(item.get("row", ""))])
    return buf.getvalue().encode("utf-8")


async def handle_ingest(msg: Message) -> None:
    payload = msg.payload
    job_id = uuid.UUID(payload["job_id"])
    bind_call_context(ingest_job_id=str(job_id))
    store = get_object_store()

    async with get_sessionmaker()() as db:
        job = await db.get(IngestJob, job_id)
        if job is None or not job.s3_key:
            return
        job.status = "processing"
        await db.commit()

    try:
        content = await store.download_bytes(payload["s3_key"])
    except Exception as exc:  # noqa: BLE001
        async with get_sessionmaker()() as db:
            job = await db.get(IngestJob, job_id)
            if job:
                job.status = "failed"
                job.error = f"download failed: {exc!r}"
                await db.commit()
        return

    result = parse_contacts(
        payload.get("filename", "upload.csv"), content, payload.get("default_country_code", "IN")
    )
    campaign_id = uuid.UUID(payload["campaign_id"])

    imported = 0
    async with get_sessionmaker()() as db:
        for i in range(0, len(result.valid), _BATCH):
            db.add_all(
                [
                    Contact(
                        campaign_id=campaign_id,
                        phone_e164=r.phone_e164,
                        customer_name=r.customer_name,
                        language=r.language,
                        timezone=r.timezone,
                        custom_fields=r.custom_fields,
                        status=ContactStatus.queued,
                    )
                    for r in result.valid[i : i + _BATCH]
                ]
            )
            await db.commit()
            imported += len(result.valid[i : i + _BATCH])
            job = await db.get(IngestJob, job_id)
            if job:
                job.imported_rows = imported
                await db.commit()

    rejected_key = None
    if result.rejected:
        rejected_key = await store.try_upload(
            f"ingest/{job_id}/rejected.csv", _rejected_csv(result.rejected), content_type="text/csv"
        )

    async with get_sessionmaker()() as db:
        job = await db.get(IngestJob, job_id)
        if job:
            job.total_rows = result.total
            job.imported_rows = imported
            job.rejected_rows_key = rejected_key
            job.status = "completed"
            if result.rejected:
                job.error = f"{len(result.rejected)} rows rejected"
            await db.commit()
    log.info("ingest_done", job_id=str(job_id), total=result.total, imported=imported)


def main() -> None:
    settings = get_settings()
    run_worker(
        StreamWorker(
            stream=settings.ingest_stream,
            group=settings.ingest_consumer_group,
            handler=handle_ingest,
            on_start=get_object_store().ensure_bucket,
        )
    )


if __name__ == "__main__":
    main()
