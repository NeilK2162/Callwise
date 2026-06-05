"""The mandatory idempotency suite (PRD §16.1) — run twice == run once.

DB-backed: requires Postgres + Redis. Skipped unless `CALLWISE_IT_DB` is set. CI runs these
against service containers (see .github/workflows/ci.yml).
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis
from sqlalchemy import func, select

from callwise.config import get_settings
from callwise.db.enums import CallStatus, ContactStatus, VerificationOutcome
from callwise.db.models import (
    CallSession,
    CallVerification,
    Campaign,
    Contact,
    Outbox,
    User,
)
from callwise.domain.idempotency import (
    advance_call_status,
    claim_contact,
    enqueue_outbox,
    register_event,
    upsert_verification,
)
from callwise.locks import redlock

from .conftest import requires_db

pytestmark = requires_db


async def _make_contact(db, *, status: ContactStatus = ContactStatus.queued) -> Contact:
    user = User(email=f"it-{uuid.uuid4()}@callwise.test", password_hash="x")
    db.add(user)
    await db.flush()
    campaign = Campaign(owner_id=user.id, name="it", provider="mock")
    db.add(campaign)
    await db.flush()
    contact = Contact(
        campaign_id=campaign.id, phone_e164="+919876500000", status=status, attempt_count=0
    )
    db.add(contact)
    await db.commit()
    return contact


async def _make_session(db) -> CallSession:
    contact = await _make_contact(db)
    sess = CallSession(
        id=uuid.uuid4(), contact_id=contact.id, provider="mock", status=CallStatus.dialing
    )
    db.add(sess)
    await db.commit()
    return sess


# ── §6.1 Atomic claim — no double-dial ──────────────────────────────────────
async def test_claim_contact_second_claim_returns_none(db):
    contact = await _make_contact(db)
    first = await claim_contact(
        db, contact_id=contact.id, campaign_id=contact.campaign_id,
        worker_id="w1", max_attempts=3, lease_ttl=180,
    )
    second = await claim_contact(
        db, contact_id=contact.id, campaign_id=contact.campaign_id,
        worker_id="w2", max_attempts=3, lease_ttl=180,
    )
    assert first is not None
    assert second is None  # the conditional UPDATE gate prevents a second dial


async def test_claim_respects_max_attempts(db):
    contact = await _make_contact(db)
    # Exhaust attempts: claim then release back to queued, repeatedly, until the cap.
    for _ in range(3):
        await claim_contact(
            db, contact_id=contact.id, campaign_id=contact.campaign_id,
            worker_id="w", max_attempts=3, lease_ttl=180,
        )
        await db.execute(
            Contact.__table__.update()
            .where(Contact.id == contact.id)
            .values(status=ContactStatus.queued)
        )
        await db.commit()
    exhausted = await claim_contact(
        db, contact_id=contact.id, campaign_id=contact.campaign_id,
        worker_id="w", max_attempts=3, lease_ttl=180,
    )
    assert exhausted is None  # attempt_count == max_attempts → not claimable


# ── §6.3 Webhook dedup ──────────────────────────────────────────────────────
async def test_register_event_dedup(db):
    event_id = f"evt-{uuid.uuid4()}"
    first = await register_event(db, event_id=event_id, event_type="t", provider="mock", raw_payload={})
    await db.commit()
    second = await register_event(db, event_id=event_id, event_type="t", provider="mock", raw_payload={})
    await db.commit()
    assert first is True
    assert second is False  # duplicate delivery is a no-op


# ── §6.3 Verification upsert ─────────────────────────────────────────────────
async def test_verification_upsert_overwrites_not_duplicates(db):
    sess = await _make_session(db)
    await upsert_verification(
        db, call_session_id=sess.id, step="verify",
        outcome=VerificationOutcome.question_answered, confidence=0.4, extracted={}, result={},
    )
    await db.commit()
    await upsert_verification(
        db, call_session_id=sess.id, step="verify",
        outcome=VerificationOutcome.appointment_booked, confidence=0.9, extracted={}, result={},
    )
    await db.commit()

    count = await db.scalar(
        select(func.count()).select_from(CallVerification).where(
            CallVerification.call_session_id == sess.id
        )
    )
    row = await db.scalar(
        select(CallVerification).where(CallVerification.call_session_id == sess.id)
    )
    assert count == 1  # one row per (session, step)
    assert row.outcome == VerificationOutcome.appointment_booked  # overwritten
    assert row.confidence == 0.9


# ── §6.3 Forward-only CAS ────────────────────────────────────────────────────
async def test_forward_only_status_absorbs_terminal(db):
    sess = await _make_session(db)
    moved = await advance_call_status(db, session_id=sess.id, new_status=CallStatus.completed)
    await db.commit()
    backward = await advance_call_status(db, session_id=sess.id, new_status=CallStatus.ringing)
    await db.commit()

    final = await db.get(CallSession, sess.id)
    assert moved is True
    assert backward is False  # re-applying past a terminal state is a no-op
    assert final.status == CallStatus.completed


# ── §9.5 Outbox exactly-once ─────────────────────────────────────────────────
async def test_outbox_dedup_key_exactly_once(db):
    sess = await _make_session(db)
    await enqueue_outbox(db, aggregate_id=sess.id, event_type="call_verified", payload={"a": 1})
    await enqueue_outbox(db, aggregate_id=sess.id, event_type="call_verified", payload={"a": 2})
    await db.commit()

    count = await db.scalar(
        select(func.count()).select_from(Outbox).where(Outbox.aggregate_id == sess.id)
    )
    assert count == 1  # dedup_key (aggregate|event_type) UNIQUE → emitted once


# ── §6.4 Distributed lock (campaign-start guard) ─────────────────────────────
async def test_redlock_is_exclusive():
    redis = Redis.from_url(get_settings().redis_url, decode_responses=False)
    key = f"it-lock-{uuid.uuid4()}"
    try:
        async with redlock(redis, key, ttl_ms=5000) as outer:
            assert outer is True
            async with redlock(redis, key, ttl_ms=5000) as inner:
                assert inner is False  # second acquirer can't take a held lock
    finally:
        await redis.aclose()
