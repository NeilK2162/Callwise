"""Twilio status callback (signature-validated, PRD §11.2)."""

from __future__ import annotations

import orjson
from fastapi import APIRouter, HTTPException, Request, status

from callwise.config import get_settings
from callwise.webhook_ingest.deps import DbSession, QueueDep
from callwise.webhook_ingest.security import verify_twilio
from callwise.webhook_ingest.service import ingest_event, stable_event_id

router = APIRouter()


@router.post("/webhooks/twilio")
async def twilio_webhook(request: Request, db: DbSession, queue: QueueDep) -> dict:
    raw = await request.body()
    signature = request.headers.get("x-twilio-signature")
    # Validate against the exact public URL we configured as the StatusCallback (behind a
    # proxy, request.url may be the internal http URL and fail validation).
    canonical_url = f"{get_settings().base_url}/api/v2/webhooks/twilio"
    if not verify_twilio(raw, signature, canonical_url):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid signature")

    form = await request.form()
    payload = {k: str(v) for k, v in form.items()}
    candidate = f"{payload.get('CallSid', '')}:{payload.get('CallStatus', '')}"
    event_id = stable_event_id("twilio", candidate, orjson.dumps(payload))
    await ingest_event(
        db,
        queue,
        provider="twilio",
        event_id=event_id,
        event_type=f"call_status.{payload.get('CallStatus', 'unknown')}",
        raw=payload,
        stream=get_settings().verify_stream,
    )
    return {"status": "ok"}
