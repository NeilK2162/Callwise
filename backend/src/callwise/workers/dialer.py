"""Dialer worker — the hot path (PRD §5.3, §6.1, §6.2, §8).

One logical step: claim a contact, place a governed call, record the attempt. Every dial
writes a `call_session` row *before* the provider call (write-ahead), so a crash mid-
dispatch leaves a recoverable record the reconciler can resolve via the provider API.
"""

from __future__ import annotations

import uuid

from sqlalchemy import update

from callwise.config import get_settings
from callwise.db.base import get_sessionmaker
from callwise.db.enums import CallDirection, CallStatus, ContactStatus
from callwise.db.models import Campaign, CallSession, Contact
from callwise.domain.idempotency import advance_call_status, claim_contact
from callwise.domain.snapshots import create_snapshot
from callwise.governors.concurrency import ConcurrencyGovernor, ConcurrencyLimitReached
from callwise.governors.rate_limiter import ProviderRateLimited, ProviderRateLimiter
from callwise.logging import bind_call_context, get_logger
from callwise.observability.metrics import DIALS_FAILED, DIALS_INITIATED
from callwise.providers.errors import TerminalProviderError
from callwise.providers.telephony.factory import get_telephony_provider
from callwise.queue.base import Message
from callwise.queue.factory import get_queue
from callwise.redis_pool import get_redis
from callwise.webhook_ingest.security import sign_context_token
from callwise.workers.base import StreamWorker, run_worker

log = get_logger(__name__)


async def _release_and_requeue(db, contact_id: uuid.UUID, session_id: uuid.UUID) -> None:
    """Capacity wasn't available — return the contact to `queued` without burning an
    attempt, and cancel the write-ahead session. The dial is re-published (PRD §8.2)."""
    await db.execute(
        update(Contact)
        .where(Contact.id == contact_id)
        .values(
            status=ContactStatus.queued,
            claimed_by=None,
            claimed_at=None,
            lease_expires_at=None,
            attempt_count=Contact.attempt_count - 1,
        )
    )
    await advance_call_status(db, session_id=session_id, new_status=CallStatus.canceled)
    await db.commit()


async def handle_dial(msg: Message) -> None:
    payload = msg.payload
    campaign_id = uuid.UUID(payload["campaign_id"])
    contact_id = uuid.UUID(payload["contact_id"])
    settings = get_settings()
    redis = get_redis()
    governor = ConcurrencyGovernor(redis)
    rate_limiter = ProviderRateLimiter(redis, settings.provider_rate_limits)
    telephony = get_telephony_provider(settings)
    worker_id = msg.meta.get("worker_id", "dialer")

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        campaign = await db.get(Campaign, campaign_id)
        if campaign is None:
            return

        claimed = await claim_contact(
            db,
            contact_id=contact_id,
            campaign_id=campaign_id,
            worker_id=worker_id,
            max_attempts=campaign.max_attempts_per_contact,
            lease_ttl=settings.concurrency_lease_ttl_seconds,
        )
        if claimed is None:
            return  # someone else won, or attempts exhausted — skip silently (idempotent)

        snapshot = await create_snapshot(
            db,
            contact_id=claimed.id,
            customer_name=claimed.customer_name,
            phone_e164=claimed.phone_e164,
            language=claimed.language,
            custom_fields=claimed.custom_fields,
            agent_id=campaign.agent_id,
            dynamic_variables={"attempt": claimed.attempt_count},
        )
        session_id = uuid.uuid4()
        db.add(
            CallSession(
                id=session_id,
                contact_id=claimed.id,
                context_snapshot_id=snapshot.id,
                direction=CallDirection.outbound,
                provider=campaign.provider,
                status=CallStatus.dialing,
            )
        )
        await db.commit()

    bind_call_context(call_session_id=str(session_id), contact_id=str(contact_id))

    # Governed dispatch: a per-campaign slot, a global slot, then a provider token.
    try:
        async with (
            governor.slot(f"campaign:{campaign_id}", campaign.max_concurrent_calls),
            governor.slot("global", settings.global_max_concurrent_calls),
        ):
            await rate_limiter.acquire(campaign.provider)
            token = sign_context_token(str(session_id))
            result = await telephony.place_call(
                to=claimed.phone_e164,
                idempotency_key=str(session_id),
                context_url=f"{settings.base_url}/api/v2/exotel/call-context?token={token}",
                max_duration_s=snapshot.max_call_duration_s,
            )
        async with sessionmaker() as db:
            await db.execute(
                update(CallSession)
                .where(CallSession.id == session_id)
                .values(provider_call_id=result.provider_call_id)
            )
            await advance_call_status(db, session_id=session_id, new_status=CallStatus.ringing)
            await db.commit()
        DIALS_INITIATED.labels(campaign=str(campaign_id)).inc()

    except (ProviderRateLimited, ConcurrencyLimitReached):
        DIALS_FAILED.labels(reason="capacity").inc()
        async with sessionmaker() as db:
            await _release_and_requeue(db, contact_id, session_id)
        await get_queue().publish(
            settings.dial_stream,
            {"campaign_id": str(campaign_id), "contact_id": str(contact_id)},
        )

    except TerminalProviderError as exc:
        DIALS_FAILED.labels(reason=exc.reason).inc()
        async with sessionmaker() as db:
            await advance_call_status(db, session_id=session_id, new_status=CallStatus.failed)
            await db.execute(
                update(Contact)
                .where(Contact.id == contact_id)
                .values(status=ContactStatus.failed, last_outcome=exc.reason)
            )
            await db.commit()


def main() -> None:
    settings = get_settings()
    run_worker(
        StreamWorker(
            stream=settings.dial_stream,
            group=settings.dial_consumer_group,
            handler=handle_dial,
        )
    )


if __name__ == "__main__":
    main()
