"""The master idempotency design (PRD §6).

Telephony, webhooks, and distributed queues are all *at-least-once*. Every
business-effecting operation here is therefore idempotent — running it twice equals
running it once. These functions are the single source of truth for that guarantee and
are covered by the mandatory "run twice == run once" suite (PRD §16.1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from callwise.db.enums import TERMINAL_CALL_STATUSES, CallStatus
from callwise.db.models import CallVerification, Outbox, ProcessedEvent

# ── §6.1 Atomic contact claim (no double-dial) ──────────────────────────────
# Conditional UPDATE that succeeds only if the contact is still claimable.
# The lease makes it self-healing: a worker that crashes after claiming releases
# the contact when the reconciler finds an expired lease and no live call_session.
_CLAIM_SQL = text(
    """
    UPDATE contacts
       SET status = 'in_progress',
           claimed_at = now(),
           claimed_by = :worker_id,
           attempt_count = attempt_count + 1,
           lease_expires_at = now() + make_interval(secs => :lease_ttl)
     WHERE id = :contact_id
       AND campaign_id = :campaign_id
       AND status = 'queued'
       AND attempt_count < :max_attempts
    RETURNING id, phone_e164, customer_name, language, custom_fields, attempt_count
    """
)


@dataclass(frozen=True)
class ClaimedContact:
    id: uuid.UUID
    phone_e164: str
    customer_name: str | None
    language: str
    custom_fields: dict
    attempt_count: int


async def claim_contact(
    session: AsyncSession,
    *,
    contact_id: uuid.UUID,
    campaign_id: uuid.UUID,
    worker_id: str,
    max_attempts: int,
    lease_ttl: int,
) -> ClaimedContact | None:
    """Win the row, or return None (someone else won / attempts exhausted) — skip silently."""
    row = (
        await session.execute(
            _CLAIM_SQL,
            {
                "contact_id": contact_id,
                "campaign_id": campaign_id,
                "worker_id": worker_id,
                "max_attempts": max_attempts,
                "lease_ttl": lease_ttl,
            },
        )
    ).first()
    await session.commit()
    if row is None:
        return None
    return ClaimedContact(
        id=row.id,
        phone_e164=row.phone_e164,
        customer_name=row.customer_name,
        language=row.language,
        custom_fields=row.custom_fields or {},
        attempt_count=row.attempt_count,
    )


# ── §6.3 Idempotent state transition (forward-only CAS) ─────────────────────
_TERMINAL_LIST = ",".join(f"'{s.value}'" for s in TERMINAL_CALL_STATUSES)
_ADVANCE_SQL = text(
    f"""
    UPDATE call_sessions
       SET status = :new_status,
           ended_at = CASE WHEN :is_terminal THEN COALESCE(ended_at, now()) ELSE ended_at END
     WHERE id = :session_id
       AND status NOT IN ({_TERMINAL_LIST})
    RETURNING id
    """  # noqa: S608 — list is built from a trusted enum, not user input
)


async def advance_call_status(
    session: AsyncSession, *, session_id: uuid.UUID, new_status: CallStatus
) -> bool:
    """Move a call forward. Re-applying a terminal state is a no-op (returns False)."""
    row = (
        await session.execute(
            _ADVANCE_SQL,
            {
                "session_id": session_id,
                "new_status": new_status.value,
                "is_terminal": new_status in TERMINAL_CALL_STATUSES,
            },
        )
    ).first()
    return row is not None


# ── §6.3 Webhook dedup (processed_events) ───────────────────────────────────
async def register_event(
    session: AsyncSession,
    *,
    event_id: str,
    event_type: str,
    provider: str,
    raw_payload: dict,
) -> bool:
    """INSERT ... ON CONFLICT DO NOTHING. Returns True if first-seen, False if duplicate."""
    stmt = (
        pg_insert(ProcessedEvent)
        .values(
            event_id=event_id,
            event_type=event_type,
            provider=provider,
            raw_payload=raw_payload,
        )
        .on_conflict_do_nothing(index_elements=[ProcessedEvent.event_id])
    )
    result = await session.execute(stmt)
    return result.rowcount == 1


# ── §6.3 Verification upsert (overwrite, never duplicate) ───────────────────
async def upsert_verification(
    session: AsyncSession, *, call_session_id: uuid.UUID, step: str, **fields
) -> None:
    """Upsert keyed on (call_session_id, step) so re-runs overwrite rather than duplicate."""
    values = {"call_session_id": call_session_id, "step": step, **fields}
    stmt = pg_insert(CallVerification).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_verification_session_step",
        set_={**fields, "updated_at": text("now()")},
    )
    await session.execute(stmt)


# ── §9.5 Transactional outbox (exactly-once event publish) ──────────────────
async def enqueue_outbox(
    session: AsyncSession,
    *,
    aggregate_id: uuid.UUID,
    event_type: str,
    payload: dict,
) -> None:
    """Insert a domain event in the SAME transaction as the state change. The dedup_key
    `(aggregate_id|event_type)` UNIQUE constraint guarantees exactly-once downstream even
    under dispatcher retries. Caller controls the transaction boundary."""
    dedup_key = f"{aggregate_id}|{event_type}"
    stmt = (
        pg_insert(Outbox)
        .values(
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            dedup_key=dedup_key,
        )
        .on_conflict_do_nothing(index_elements=[Outbox.dedup_key])
    )
    await session.execute(stmt)
