"""Exotel call-status callback (PRD §11.2)."""

from __future__ import annotations

import orjson
from fastapi import APIRouter, Request

from callwise.config import get_settings
from callwise.webhook_ingest.deps import DbSession, QueueDep
from callwise.webhook_ingest.service import ingest_event, stable_event_id

router = APIRouter()


@router.post("/webhooks/exotel/call-status")
async def exotel_call_status(request: Request, db: DbSession, queue: QueueDep) -> dict:
    # Exotel posts form-encoded status callbacks.
    form = await request.form()
    payload = {k: str(v) for k, v in form.items()}
    raw = orjson.dumps(payload)
    # Correlate via CustomField (our call_session_id) + Status for a stable, ordered id.
    candidate = f"{payload.get('CallSid', '')}:{payload.get('Status', '')}"
    event_id = stable_event_id("exotel", candidate, raw)
    await ingest_event(
        db,
        queue,
        provider="exotel",
        event_id=event_id,
        event_type=f"call_status.{payload.get('Status', 'unknown')}",
        raw=payload,
        stream=get_settings().verify_stream,
    )
    return {"status": "ok"}
