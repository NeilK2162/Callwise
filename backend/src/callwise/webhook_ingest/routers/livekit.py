"""LiveKit agent post-call webhook (PRD §5.4).

Our own LiveKit agent (providers/conversation/livekit_agent.py) POSTs a normalized
transcript here when a call ends. Flows through the same dedup → enqueue → verify pipeline
as every other provider. In production, protect this with a shared secret / signature
(the agent runs in our trust boundary, but defense in depth still applies).
"""

from __future__ import annotations

import orjson
from fastapi import APIRouter, Request

from callwise.config import get_settings
from callwise.webhook_ingest.deps import DbSession, QueueDep
from callwise.webhook_ingest.service import ingest_event, stable_event_id

router = APIRouter()


@router.post("/webhooks/livekit")
async def livekit_webhook(request: Request, db: DbSession, queue: QueueDep) -> dict:
    raw = await request.body()
    payload = orjson.loads(raw or b"{}")
    event_id = stable_event_id("livekit", payload.get("call_session_id"), raw)
    await ingest_event(
        db,
        queue,
        provider="livekit",
        event_id=event_id,
        event_type="post_call_transcription",
        raw=payload,
        stream=get_settings().verify_stream,
    )
    return {"status": "ok"}
