"""Exotel call-status callback (PRD §11.2).

Exotel posts the StatusCallback as JSON (when StatusCallbackContentType=application/json)
or form-encoded. We persist the raw payload and enqueue; the verification worker
normalizes Exotel's fields (Status, CustomField=our call_session_id, CallSid, Legs[].
AnsweredBy) into our state machine.
"""

from __future__ import annotations

import orjson
from fastapi import APIRouter, Request

from callwise.config import get_settings
from callwise.webhook_ingest.deps import DbSession, QueueDep
from callwise.webhook_ingest.service import ingest_event, stable_event_id

router = APIRouter()


async def _read_payload(request: Request) -> dict:
    body = await request.body()
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            return orjson.loads(body or b"{}")
        except orjson.JSONDecodeError:
            return {}
    form = await request.form()
    return {k: str(v) for k, v in form.items()}


@router.post("/webhooks/exotel/call-status")
async def exotel_call_status(request: Request, db: DbSession, queue: QueueDep) -> dict:
    payload = await _read_payload(request)
    # Correlate via CustomField (our call_session_id) + Status for a stable, ordered id.
    candidate = f"{payload.get('CallSid', '')}:{payload.get('Status', '')}"
    event_id = stable_event_id("exotel", candidate, orjson.dumps(payload))
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
