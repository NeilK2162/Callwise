"""Transactional-outbox dispatcher (PRD §9.5).

The reconciler runs this on a tick. It polls unpublished `outbox` rows, publishes each to
the message bus, and stamps `published_at`. If a publish fails, the row stays and is
retried next tick. The `dedup_key` UNIQUE constraint (set at insert time, see
`domain.idempotency.enqueue_outbox`) guarantees exactly-once delivery downstream even
under dispatcher retries or redelivery.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from callwise.db.models import Outbox
from callwise.logging import get_logger

log = get_logger(__name__)

Publisher = Callable[[str, dict], Awaitable[None]]


async def dispatch_outbox(
    session: AsyncSession, publish: Publisher, *, batch_size: int = 200
) -> int:
    """Publish a batch of unpublished events. Returns the number published this tick."""
    rows = (
        await session.scalars(
            select(Outbox)
            .where(Outbox.published_at.is_(None))
            .order_by(Outbox.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)  # multiple dispatchers won't collide
        )
    ).all()

    published = 0
    for row in rows:
        try:
            await publish(row.event_type, {"id": row.id, **row.payload})
        except Exception:  # noqa: BLE001 — leave row unpublished, retry next tick
            log.warning("outbox_publish_failed", outbox_id=row.id, event=row.event_type)
            continue
        await session.execute(
            update(Outbox).where(Outbox.id == row.id).values(published_at=func.now())
        )
        published += 1

    await session.commit()
    return published
