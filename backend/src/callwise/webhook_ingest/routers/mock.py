"""Internal mock-provider webhook (local dev / load harness only).

The mock telephony provider POSTs synthetic post-call events here; they flow through the
exact same dedup → persist → enqueue path as a real provider webhook. Not mounted in
production (the mock provider isn't used there).
"""

from __future__ import annotations

import orjson
from fastapi import APIRouter, Request

from callwise.config import get_settings
from callwise.webhook_ingest.deps import DbSession, QueueDep
from callwise.webhook_ingest.service import ingest_event, stable_event_id

router = APIRouter()


@router.post("/webhooks/mock")
async def mock_webhook(request: Request, db: DbSession, queue: QueueDep) -> dict:
    raw = await request.body()
    payload = orjson.loads(raw or b"{}")
    candidate = f"{payload.get('call_session_id', '')}:{payload.get('status', '')}"
    event_id = stable_event_id("mock", candidate, raw)
    await ingest_event(
        db,
        queue,
        provider="mock",
        event_id=event_id,
        event_type=f"mock.{payload.get('status', 'unknown')}",
        raw=payload,
        stream=get_settings().verify_stream,
    )
    return {"status": "ok"}
