"""Dial orchestration — enqueue governed dials (PRD §5.2, §8.4).

The orchestrator turns `queued` contacts into dial tasks on `dial:stream`. The claim in
the dialer is idempotent, so enqueuing is always safe to retry and a contact can never be
double-dialed even if it lands on the stream twice. Compliance filtering (calling window,
DND) is applied here at enqueue time and again as a pre-dial check in the dialer
(defense in depth) — see `callwise.compliance`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from callwise.compliance import is_callable_now
from callwise.config import get_settings
from callwise.db.enums import ContactStatus
from callwise.db.models import Campaign, Contact
from callwise.queue.base import Queue


async def enqueue_single_dial(
    queue: Queue, *, campaign_id: uuid.UUID, contact_id: uuid.UUID
) -> None:
    settings = get_settings()
    await queue.ensure_group(settings.dial_stream, settings.dial_consumer_group)
    await queue.publish(
        settings.dial_stream,
        {"campaign_id": str(campaign_id), "contact_id": str(contact_id)},
        idempotency_key=f"dial:{contact_id}",
    )


async def enqueue_dials_for_campaign(
    db: AsyncSession, queue: Queue, *, campaign: Campaign, max_batch: int = 5000
) -> int:
    """Enqueue dials for queued, in-window, non-suppressed contacts. Returns count enqueued.

    Bounded by `max_batch` so a 5M-contact campaign is paced rather than dumped on the
    stream all at once (edge case #37); the reconciler/orchestrator re-runs to drain more.
    """
    settings = get_settings()
    await queue.ensure_group(settings.dial_stream, settings.dial_consumer_group)

    contacts = (
        await db.scalars(
            select(Contact)
            .where(Contact.campaign_id == campaign.id, Contact.status == ContactStatus.queued)
            .limit(max_batch)
        )
    ).all()

    enqueued = 0
    for contact in contacts:
        if not is_callable_now(contact, campaign):
            continue  # out of calling window / suppressed → deferred, not dialed
        await queue.publish(
            settings.dial_stream,
            {"campaign_id": str(campaign.id), "contact_id": str(contact.id)},
            idempotency_key=f"dial:{contact.id}",
        )
        enqueued += 1
    return enqueued
