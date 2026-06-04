"""Verification worker — the post-call pipeline (PRD §5.5, §7.3).

Three independently idempotent, independently retryable steps keyed on
`(call_session_id, step)`: transcript assembly, verification, summarization. One LLM call
= one customer, ever (edge case #26). Bad JSON never crashes the worker — it falls back to
`undetermined` (edge case #24).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update

from callwise.config import get_settings
from callwise.db.base import get_sessionmaker
from callwise.db.enums import CallStatus, ContactStatus, VerificationOutcome
from callwise.db.models import (
    CallSession,
    Campaign,
    Contact,
    ProcessedEvent,
    Recording,
    Transcript,
)
from callwise.domain.idempotency import advance_call_status, enqueue_outbox, upsert_verification
from callwise.domain.snapshots import load_snapshot
from callwise.domain.verification import verify_transcript
from callwise.events import publish_card_event
from callwise.logging import bind_call_context, get_logger
from callwise.redis_pool import get_redis
from callwise.observability.metrics import DIALS_FAILED, VERIFICATION_CONFIDENCE
from callwise.orchestration import enqueue_single_dial
from callwise.providers.conversation.elevenlabs import session_id_from_payload
from callwise.providers.conversation.factory import get_conversation_provider
from callwise.providers.llm.factory import get_llm_provider
from callwise.queue.base import Message
from callwise.queue.factory import get_queue
from callwise.reliability.retry import RetryClass, classify_reason
from callwise.workers.base import StreamWorker, run_worker

log = get_logger(__name__)

# Terminal call statuses that retry (within attempt limits) vs. those that don't.
_RETRYABLE_STATUSES = {CallStatus.no_answer, CallStatus.busy}


async def _handle_terminal_status(db, sess: CallSession, status_str: str) -> None:
    """A non-answered terminal status callback (no transcript): advance the call and either
    requeue the contact (retryable, attempts remain) or mark it terminal."""
    try:
        call_status = CallStatus(status_str)
    except ValueError:
        call_status = CallStatus.failed
    await advance_call_status(db, session_id=sess.id, new_status=call_status)

    contact = await db.get(Contact, sess.contact_id)
    if contact is None:
        await db.commit()
        return
    campaign = await db.get(Campaign, contact.campaign_id)
    max_attempts = campaign.max_attempts_per_contact if campaign else 3
    DIALS_FAILED.labels(reason=status_str).inc()

    retryable = (
        call_status in _RETRYABLE_STATUSES
        and classify_reason(status_str) is RetryClass.retryable
        and contact.attempt_count < max_attempts
    )
    contact.last_outcome = status_str
    if retryable:
        contact.status = ContactStatus.queued
        contact.claimed_by = None
        contact.claimed_at = None
        contact.lease_expires_at = None
        await db.commit()
        await enqueue_single_dial(get_queue(), campaign_id=contact.campaign_id, contact_id=contact.id)
        log.info("call_retry_scheduled", status=status_str, attempt=contact.attempt_count)
    else:
        if call_status is CallStatus.failed:
            contact.status = ContactStatus.failed
        elif contact.attempt_count >= max_attempts:
            contact.status = ContactStatus.max_attempts
        else:
            contact.status = ContactStatus.no_answer
        await db.commit()
        log.info("call_terminal", status=status_str, contact_status=contact.status.value)


async def _by_provider_call_id(db, provider_call_id: str | None) -> CallSession | None:
    if not provider_call_id:
        return None
    return await db.scalar(
        select(CallSession).where(CallSession.provider_call_id == provider_call_id)
    )


async def _resolve_session(db, provider: str, raw: dict) -> CallSession | None:
    """Correlate a provider payload to our call_session via each provider's echo field:
    ElevenLabs → injected dynamic variable; Exotel → CustomField; mock → call_session_id;
    else fall back to provider_call_id → call_sessions.provider_call_id."""
    sid: str | None = None
    if provider == "elevenlabs":
        sid = session_id_from_payload(raw)
        if sid is None:
            return await _by_provider_call_id(db, (raw.get("data", {}) or {}).get("conversation_id"))
    elif provider == "exotel":
        sid = raw.get("CustomField")
        if not sid:
            return await _by_provider_call_id(db, raw.get("CallSid"))
    elif provider == "mock":
        sid = raw.get("call_session_id")
    else:  # twilio and others correlate by their call id
        return await _by_provider_call_id(db, raw.get("CallSid") or raw.get("provider_call_id"))

    if sid:
        try:
            return await db.get(CallSession, uuid.UUID(sid))
        except ValueError:
            return None
    return await _by_provider_call_id(db, raw.get("provider_call_id") or raw.get("CallSid"))


# Status strings that mean "answered" (advance the call; the transcript event finalizes it).
_ANSWERED = {"answered", "in_progress", "completed", "ringing", "dialing"}


def _normalize_status(provider: str, raw: dict) -> str:
    """Map a provider status callback to our vocabulary: answered | no_answer | busy |
    voicemail | failed | canceled."""
    if provider == "exotel":
        from callwise.providers.telephony.exotel import map_exotel_status

        status = map_exotel_status(raw.get("Status"))
        answered_by = _exotel_answered_by(raw)
        if status is CallStatus.completed:
            return "voicemail" if answered_by == "Machine" else "answered"
        return status.value
    if provider == "twilio":
        twilio_map = {
            "completed": "answered",
            "no-answer": "no_answer",
            "busy": "busy",
            "failed": "failed",
            "canceled": "canceled",
        }
        return twilio_map.get(str(raw.get("CallStatus", "")).lower(), "failed")
    # mock posts our own status values directly.
    return str(raw.get("status", "failed"))


def _exotel_answered_by(raw: dict) -> str | None:
    if raw.get("AnsweredBy"):
        return raw["AnsweredBy"]
    legs = raw.get("Legs") or []
    if legs and isinstance(legs, list) and isinstance(legs[0], dict):
        return legs[0].get("AnsweredBy")
    return None


async def handle_verification(msg: Message) -> None:
    event_id = msg.payload["event_id"]
    provider = msg.payload.get("provider", "")
    sessionmaker = get_sessionmaker()
    conversation = get_conversation_provider()
    llm = get_llm_provider()

    async with sessionmaker() as db:
        event = await db.get(ProcessedEvent, event_id)
        if event is None:
            log.warning("verify_event_missing", event_id=event_id)
            return
        raw = event.raw_payload or {}

        sess = await _resolve_session(db, provider, raw)
        if sess is None:
            log.warning("verify_session_unresolved", event_id=event_id, provider=provider)
            return  # reconciler will retry correlation; never crash the worker

        bind_call_context(call_session_id=str(sess.id))

        # Dispatch: a transcription event (conversation provider) runs the LLM pipeline;
        # a status callback (telephony provider) just advances state / handles retries.
        is_transcription = provider == "elevenlabs" or (
            provider == "mock" and raw.get("status") == CallStatus.completed.value
        )
        if not is_transcription:
            status_str = _normalize_status(provider, raw)
            if status_str in _ANSWERED:
                await advance_call_status(db, session_id=sess.id, new_status=CallStatus.in_progress)
                await db.commit()
                return
            await _handle_terminal_status(db, sess, status_str)
            return

        # 1) Transcript assembly (idempotent: one transcript row per session).
        parsed = conversation.parse_post_call(raw)
        existing = await db.scalar(
            select(Transcript).where(Transcript.call_session_id == sess.id)
        )
        if existing is None:
            db.add(
                Transcript(
                    call_session_id=sess.id,
                    turns=parsed.turns,
                    summary=parsed.summary,
                )
            )
            if parsed.recording_url:
                db.add(
                    Recording(
                        call_session_id=sess.id,
                        s3_key=parsed.recording_url,
                        duration_s=parsed.duration_s,
                        uploaded=True,
                    )
                )
        if parsed.duration_s is not None:
            await advance_call_status(db, session_id=sess.id, new_status=CallStatus.completed)
            await db.execute(
                update(CallSession)
                .where(CallSession.id == sess.id)
                .values(duration_s=parsed.duration_s)
            )
        await db.commit()

        # 2) Verification (scoped to THIS customer + THIS call only).
        snapshot = (
            await load_snapshot(db, sess.context_snapshot_id)
            if sess.context_snapshot_id
            else None
        )
        expected = snapshot.custom_fields if snapshot else {}
        language = snapshot.language if snapshot else "en"
        result = await verify_transcript(
            llm, expected=expected, turns=parsed.turns, language=language
        )

        confidence = float(result.get("confidence", 0.0))
        try:
            outcome = VerificationOutcome(result.get("outcome", "undetermined"))
        except ValueError:
            outcome = VerificationOutcome.undetermined
        VERIFICATION_CONFIDENCE.observe(confidence)

        await upsert_verification(
            db,
            call_session_id=sess.id,
            step="verify",
            outcome=outcome,
            responder_type=result.get("responder_type"),
            confidence=confidence,
            extracted=result.get("extracted", {}),
            result=result,
        )

        # 3) Apply outcome tags to the contact (idempotent write).
        await db.execute(
            update(Contact)
            .where(Contact.id == sess.contact_id)
            .values(
                status=ContactStatus.completed,
                last_outcome=outcome.value,
                outcome_tags={"outcome": outcome.value, "confidence": confidence,
                              "extracted": result.get("extracted", {})},
            )
        )

        # Emit the domain event exactly-once for downstream consumers.
        await enqueue_outbox(
            db,
            aggregate_id=sess.id,
            event_type="call_verified",
            payload={"outcome": outcome.value, "confidence": confidence},
        )
        await db.commit()
        log.info("call_verified", outcome=outcome.value, confidence=confidence)

        # Push a live update so the dashboard feed updates in real time (PRD §18.1).
        owner_id = await db.scalar(
            select(Campaign.owner_id)
            .join(Contact, Contact.campaign_id == Campaign.id)
            .where(Contact.id == sess.contact_id)
        )
        if owner_id is not None:
            await publish_card_event(
                get_redis(),
                owner_id,
                {"type": "card_updated", "call_session_id": str(sess.id), "outcome": outcome.value},
            )


def main() -> None:
    settings = get_settings()
    run_worker(
        StreamWorker(
            stream=settings.verify_stream,
            group=settings.verify_consumer_group,
            handler=handle_verification,
        )
    )


if __name__ == "__main__":
    main()
