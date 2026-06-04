"""Shared webhook ingest path (PRD §6.3, §11.2).

All webhook endpoints follow the same shape:
    verify signature → dedup (`processed_events`) → persist raw → enqueue → ACK 200 (<200ms)
Heavy work (transcript assembly, verification) happens in a worker, never in the request.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from callwise.domain.idempotency import register_event
from callwise.logging import get_logger
from callwise.observability.metrics import WEBHOOK_DEDUP_HITS, WEBHOOK_RECEIVED
from callwise.queue.base import Queue

log = get_logger(__name__)


def stable_event_id(provider: str, candidate: str | None, raw_body: bytes) -> str:
    """Prefer the provider's own event id; otherwise hash the payload so identical
    redeliveries collapse to the same id and dedup catches them (PRD §6.3)."""
    if candidate:
        return f"{provider}:{candidate}"
    digest = hashlib.sha256(raw_body).hexdigest()[:32]
    return f"{provider}:{digest}"


async def ingest_event(
    db: AsyncSession,
    queue: Queue,
    *,
    provider: str,
    event_id: str,
    event_type: str,
    raw: dict,
    stream: str,
) -> bool:
    """Dedup + persist + enqueue. Returns True if first-seen (enqueued), False if duplicate."""
    WEBHOOK_RECEIVED.labels(provider=provider, type=event_type).inc()

    first_seen = await register_event(
        db, event_id=event_id, event_type=event_type, provider=provider, raw_payload=raw
    )
    await db.commit()

    if not first_seen:
        WEBHOOK_DEDUP_HITS.inc()
        log.info("webhook_duplicate_ignored", provider=provider, event_id=event_id)
        return False

    await queue.publish(
        stream,
        {"event_id": event_id, "event_type": event_type, "provider": provider},
        idempotency_key=event_id,
    )
    return True
