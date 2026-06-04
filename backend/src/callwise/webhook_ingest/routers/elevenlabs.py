"""ElevenLabs webhooks: post_call_transcription / audio / failure (HMAC, PRD §11.2)."""

from __future__ import annotations

import orjson
from fastapi import APIRouter, HTTPException, Request, status

from callwise.config import get_settings
from callwise.webhook_ingest.deps import DbSession, QueueDep
from callwise.webhook_ingest.security import verify_elevenlabs
from callwise.webhook_ingest.service import ingest_event, stable_event_id

router = APIRouter()


@router.post("/webhooks/elevenlabs")
async def elevenlabs_webhook(request: Request, db: DbSession, queue: QueueDep) -> dict:
    raw = await request.body()
    signature = request.headers.get("elevenlabs-signature") or request.headers.get(
        "x-elevenlabs-signature"
    )
    if not verify_elevenlabs(raw, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid signature")

    payload = orjson.loads(raw or b"{}")
    event_type = payload.get("type", "post_call_transcription")
    event_id = stable_event_id(
        "elevenlabs", payload.get("event_id") or payload.get("conversation_id"), raw
    )
    await ingest_event(
        db,
        queue,
        provider="elevenlabs",
        event_id=event_id,
        event_type=event_type,
        raw=payload,
        stream=get_settings().verify_stream,
    )
    return {"status": "ok"}
