"""Reconciler / sweeper — the safety net for a lossy telephony world (PRD §5.6).

Runs on a schedule, leader-elected so only one replica sweeps at a time. Assumes any
in-flight thing might be silently lost and resolves it:
  * orphan contacts (in_progress, expired lease, no live session) → back to queued
  * stale sessions (non-terminal past TTL) → resolve true state via the provider API
  * transactional outbox → publish pending domain events
Each pass is idempotent.
"""

from __future__ import annotations

import asyncio
import signal
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from callwise.config import get_settings
from callwise.db.base import get_sessionmaker
from callwise.db.enums import CallStatus, ContactStatus
from callwise.db.models import CallSession, Contact
from callwise.domain.idempotency import advance_call_status
from callwise.locks import redlock
from callwise.logging import configure_logging, get_logger
from callwise.providers.telephony.factory import get_telephony_provider
from callwise.redis_pool import get_redis
from callwise.reliability.outbox import dispatch_outbox

log = get_logger(__name__)

_NON_TERMINAL = (CallStatus.dialing, CallStatus.ringing, CallStatus.in_progress)


async def _recover_orphan_contacts(db) -> int:
    """Contacts stuck in_progress with an expired lease and no live session → queued."""
    now = datetime.now(UTC)
    live = (
        select(CallSession.id)
        .where(
            CallSession.contact_id == Contact.id,
            CallSession.status.in_(_NON_TERMINAL),
        )
        .exists()
    )
    result = await db.execute(
        update(Contact)
        .where(
            Contact.status == ContactStatus.in_progress,
            Contact.lease_expires_at < now,
            ~live,
        )
        .values(status=ContactStatus.queued, claimed_by=None, claimed_at=None, lease_expires_at=None)
    )
    await db.commit()
    return result.rowcount or 0


async def _sweep_stale_sessions(db, stale_ttl: int) -> int:
    """Sessions stuck non-terminal past TTL → query provider for true state and close."""
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_ttl)
    stale = list(
        await db.scalars(
            select(CallSession)
            .where(CallSession.status.in_(_NON_TERMINAL), CallSession.started_at < cutoff)
            .limit(200)
        )
    )
    resolved = 0
    for sess in stale:
        # TODO: select the adapter by sess.provider instead of the configured default.
        provider = get_telephony_provider()
        try:
            true_status = (
                await provider.get_call_status(sess.provider_call_id)
                if sess.provider_call_id
                else CallStatus.failed
            )
        except Exception:  # noqa: BLE001
            true_status = CallStatus.failed
        if await advance_call_status(db, session_id=sess.id, new_status=true_status):
            resolved += 1
    await db.commit()
    return resolved


async def _publish(event_type: str, payload: dict) -> None:
    # TODO: publish to the real domain-event bus / consumers. For now, log.
    log.info("domain_event_published", event_type=event_type, **payload)


async def _tick() -> None:
    settings = get_settings()
    async with get_sessionmaker()() as db:
        orphans = await _recover_orphan_contacts(db)
        stale = await _sweep_stale_sessions(db, settings.session_stale_ttl_seconds)
        published = await dispatch_outbox(db, _publish)
    if orphans or stale or published:
        log.info("reconciler_tick", orphans=orphans, stale=stale, published=published)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.app_env != "dev")
    redis = get_redis()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop.set())

    log.info("reconciler_started", interval=settings.reconciler_interval_seconds)
    while not stop.is_set():
        # Leader election: only one replica sweeps per tick (singleton work, PRD §15.1).
        async with redlock(
            redis, "reconciler-leader", ttl_ms=settings.reconciler_interval_seconds * 2000
        ) as leader:
            if leader:
                try:
                    await _tick()
                except Exception:  # noqa: BLE001 — never let one bad tick kill the loop
                    log.exception("reconciler_tick_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.reconciler_interval_seconds)
        except TimeoutError:
            pass
    log.info("reconciler_stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
