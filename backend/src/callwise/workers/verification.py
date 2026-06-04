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
from callwise.db.enums import CallStatus, ContactStatus
from callwise.db.models import (
    CallSession,
    Contact,
    ProcessedEvent,
    Transcript,
)
from callwise.domain.idempotency import advance_call_status, enqueue_outbox, upsert_verification
from callwise.domain.snapshots import load_snapshot
from callwise.domain.verification import verify_transcript
from callwise.logging import bind_call_context, get_logger
from callwise.observability.metrics import VERIFICATION_CONFIDENCE
from callwise.providers.conversation.factory import get_conversation_provider
from callwise.providers.llm.factory import get_llm_provider
from callwise.queue.base import Message
from callwise.workers.base import StreamWorker, run_worker

log = get_logger(__name__)


async def _resolve_session(db, raw: dict) -> CallSession | None:
    """Correlate a provider post-call payload to our call_session.

    TODO: this is the main provider-specific seam. Prefer our own id if the provider
    echoes it (CustomField / dynamic var); else map provider_call_id → call_sessions.
    """
    sid = raw.get("call_session_id")
    if sid:
        return await db.get(CallSession, uuid.UUID(sid))
    provider_call_id = raw.get("provider_call_id") or raw.get("CallSid")
    if provider_call_id:
        return await db.scalar(
            select(CallSession).where(CallSession.provider_call_id == provider_call_id)
        )
    return None


async def handle_verification(msg: Message) -> None:
    event_id = msg.payload["event_id"]
    sessionmaker = get_sessionmaker()
    conversation = get_conversation_provider()
    llm = get_llm_provider()

    async with sessionmaker() as db:
        event = await db.get(ProcessedEvent, event_id)
        if event is None:
            log.warning("verify_event_missing", event_id=event_id)
            return
        raw = event.raw_payload or {}

        sess = await _resolve_session(db, raw)
        if sess is None:
            log.warning("verify_session_unresolved", event_id=event_id)
            return  # reconciler will retry correlation; never crash the worker

        bind_call_context(call_session_id=str(sess.id))

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
        outcome = result.get("outcome", "undetermined")
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
                last_outcome=outcome,
                outcome_tags={"outcome": outcome, "confidence": confidence,
                              "extracted": result.get("extracted", {})},
            )
        )

        # Emit the domain event exactly-once for downstream consumers.
        await enqueue_outbox(
            db,
            aggregate_id=sess.id,
            event_type="call_verified",
            payload={"outcome": outcome, "confidence": confidence},
        )
        await db.commit()
        log.info("call_verified", outcome=outcome, confidence=confidence)


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
