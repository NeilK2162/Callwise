"""Verification worker — the post-call pipeline (PRD §5.5, §7.3).

Three independently idempotent, independently retryable steps keyed on
`(call_session_id, step)`: transcript assembly, verification, summarization. One LLM call
= one customer, ever (edge case #26). Bad JSON never crashes the worker — it falls back to
`undetermined` (edge case #24).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update

from callwise.agent_tools import load_outcome
from callwise.config import get_settings
from callwise.db.base import get_sessionmaker
from callwise.db.enums import (
    CallDirection,
    CallStatus,
    CampaignStatus,
    ContactStatus,
    VerificationOutcome,
)
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
from callwise.domain.suppression import suppress
from callwise.domain.verification import verify_transcript
from callwise.events import publish_card_event
from callwise.governors.token_budget import TokenBudgetLimiter
from callwise.logging import bind_call_context, get_logger
from callwise.observability.metrics import COST_MICROS, DIALS_FAILED, VERIFICATION_CONFIDENCE
from callwise.orchestration import enqueue_single_dial
from callwise.providers.conversation.elevenlabs import (
    caller_id_from_payload,
    session_id_from_payload,
)
from callwise.providers.conversation.factory import get_conversation_provider
from callwise.providers.llm.factory import get_llm_provider
from callwise.queue.base import Message
from callwise.queue.factory import get_queue
from callwise.redis_pool import get_redis
from callwise.reliability.retry import RetryClass, classify_reason
from callwise.storage import get_object_store
from callwise.workers.base import StreamWorker, run_worker

log = get_logger(__name__)

# Terminal call statuses that retry (within attempt limits) vs. those that don't.
_RETRYABLE_STATUSES = {CallStatus.no_answer, CallStatus.busy}


def _estimate_tokens(expected: dict, turns: list[dict], max_output: int) -> int:
    """Rough token estimate (~4 chars/token) for the TPM budget + spend accrual (PRD §19)."""
    chars = len(str(expected)) + sum(len(str(t.get("text", ""))) for t in turns)
    return chars // 4 + 200 + max_output  # prompt overhead + capped output


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
    elif provider in ("mock", "livekit"):
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
        call_status = str(raw.get("CallStatus", "")).lower()
        if call_status == "completed" and str(raw.get("AnsweredBy", "")).startswith("machine"):
            return "voicemail"  # AMD detected an answering machine
        twilio_map = {
            "completed": "answered",
            "no-answer": "no_answer",
            "busy": "busy",
            "failed": "failed",
            "canceled": "canceled",
        }
        return twilio_map.get(call_status, "failed")
    # mock posts our own status values directly.
    return str(raw.get("status", "failed"))


def _exotel_answered_by(raw: dict) -> str | None:
    if raw.get("AnsweredBy"):
        return raw["AnsweredBy"]
    legs = raw.get("Legs") or []
    if legs and isinstance(legs, list) and isinstance(legs[0], dict):
        return legs[0].get("AnsweredBy")
    return None


async def _reverify(call_session_id: str) -> None:
    """Manual re-verify: re-run the LLM over the stored transcript (idempotent upsert)."""
    llm = get_llm_provider()
    async with get_sessionmaker()() as db:
        sess = await db.get(CallSession, uuid.UUID(call_session_id))
        transcript = (
            await db.scalar(select(Transcript).where(Transcript.call_session_id == sess.id))
            if sess
            else None
        )
        if sess is None or transcript is None:
            return
        bind_call_context(call_session_id=str(sess.id))
        snapshot = (
            await load_snapshot(db, sess.context_snapshot_id) if sess.context_snapshot_id else None
        )
        result = await verify_transcript(
            llm,
            expected=snapshot.custom_fields if snapshot else {},
            turns=transcript.turns,
            language=snapshot.language if snapshot else "en",
        )
        try:
            outcome = VerificationOutcome(result.get("outcome", "undetermined"))
        except ValueError:
            outcome = VerificationOutcome.undetermined
        await upsert_verification(
            db, call_session_id=sess.id, step="verify", outcome=outcome,
            responder_type=result.get("responder_type"),
            confidence=float(result.get("confidence", 0.0)),
            extracted=result.get("extracted", {}), result=result,
        )
        await db.execute(
            update(Contact).where(Contact.id == sess.contact_id).values(last_outcome=outcome.value)
        )
        await db.commit()
        log.info("manual_reverify_done", outcome=outcome.value)


async def _ensure_inbound_session(
    db,
    raw: dict,
    *,
    provider: str = "livekit",
    from_number: str | None = None,
    provider_call_id: str | None = None,
) -> CallSession | None:
    """Create an inbound Contact + CallSession for a caller-initiated call (PRD §0.2), so it
    lands as a query card. Attributed to INBOUND_CAMPAIGN_ID, else the newest campaign.
    Orchestrator-neutral: works for the LiveKit agent and the ElevenLabs Agent alike. The
    session's `provider_call_id` echoes the orchestrator's call id, so a redelivery/retry
    correlates to this same session instead of creating a duplicate."""
    settings = get_settings()
    campaign_id = None
    if settings.inbound_campaign_id:
        try:
            campaign_id = uuid.UUID(settings.inbound_campaign_id)
        except ValueError:
            campaign_id = None
    if campaign_id is None:
        campaign_id = await db.scalar(
            select(Campaign.id).order_by(Campaign.created_at.desc()).limit(1)
        )
    if campaign_id is None:
        return None  # nothing to attribute the inbound call to

    contact = Contact(
        campaign_id=campaign_id,
        phone_e164=str(from_number or raw.get("from_number") or "unknown")[:20],
        status=ContactStatus.in_progress,
    )
    db.add(contact)
    await db.flush()
    try:
        sid = uuid.UUID(raw["call_session_id"])
    except (KeyError, ValueError):
        sid = uuid.uuid4()
    sess = CallSession(
        id=sid,
        contact_id=contact.id,
        direction=CallDirection.inbound,
        provider=provider,
        provider_call_id=provider_call_id or raw.get("provider_call_id"),
        status=CallStatus.in_progress,
    )
    db.add(sess)
    await db.commit()
    return sess


async def handle_verification(msg: Message) -> None:
    provider = msg.payload.get("provider", "")
    if provider == "reverify":
        await _reverify(msg.payload["call_session_id"])
        return

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

        sess = await _resolve_session(db, provider, raw)
        el_stash: dict = {}
        if provider == "elevenlabs":
            # Outcomes the ElevenLabs agent recorded mid-call (book/message/opt-out), keyed by
            # conversation_id — the authoritative record of what actually happened.
            conversation_id = (raw.get("data", {}) or {}).get("conversation_id")
            el_stash = await load_outcome(conversation_id)
            if sess is None:
                # Caller dialed the agent directly (no pre-created session) — make one so the
                # call becomes a query card, attributed to the inbound campaign.
                sess = await _ensure_inbound_session(
                    db,
                    raw,
                    provider="elevenlabs",
                    from_number=el_stash.get("caller_id") or caller_id_from_payload(raw),
                    provider_call_id=conversation_id,
                )
        elif sess is None and provider == "livekit" and raw.get("direction") == "inbound":
            # Inbound call (caller dialed us) — no pre-created session. Create one so the
            # call becomes a query card, attributed to the inbound campaign.
            sess = await _ensure_inbound_session(db, raw)
        if sess is None:
            log.warning("verify_session_unresolved", event_id=event_id, provider=provider)
            return  # reconciler will retry correlation; never crash the worker

        bind_call_context(call_session_id=str(sess.id))

        # Dispatch: a transcription event (conversation provider) runs the LLM pipeline;
        # a status callback (telephony provider) just advances state / handles retries.
        is_transcription = provider in ("elevenlabs", "livekit") or (
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

        # --- Transcription path: parse → verify (ONE LLM call) → persist (PRD §19) ---
        settings = get_settings()
        parsed = conversation.parse_post_call(raw)

        snapshot = (
            await load_snapshot(db, sess.context_snapshot_id)
            if sess.context_snapshot_id
            else None
        )
        expected = snapshot.custom_fields if snapshot else {}
        language = snapshot.language if snapshot else "en"

        # Gate LLM spend on the per-minute token budget (queues under surge, never drops).
        has_customer_speech = any(
            t.get("role") == "customer" and str(t.get("text", "")).strip() for t in parsed.turns
        )
        est_tokens = _estimate_tokens(expected, parsed.turns, settings.llm_max_output_tokens)
        if has_customer_speech:
            await TokenBudgetLimiter(get_redis(), settings.llm_tokens_per_minute_budget).acquire(
                est_tokens
            )

        # One call: classification + extraction + summary (transcript already trimmed).
        result = await verify_transcript(llm, expected=expected, turns=parsed.turns, language=language)
        confidence = float(result.get("confidence", 0.0))
        try:
            outcome = VerificationOutcome(result.get("outcome", "undetermined"))
        except ValueError:
            outcome = VerificationOutcome.undetermined

        # The agent's own signals are authoritative — they reflect what actually happened on
        # the call, so they override the LLM's transcript read (PRD §12 edge cases).
        result.setdefault("extracted", {})
        # ElevenLabs path: overlay the authoritative mid-call tool outcomes onto `raw` so the
        # same override logic below applies regardless of which engine ran the call.
        if el_stash:
            if el_stash.get("opted_out"):
                raw["opted_out"] = True
            if el_stash.get("booking"):
                raw["booking"] = el_stash["booking"]
            if el_stash.get("message") and not raw.get("message"):
                raw["message"] = el_stash["message"]
        booking, message = raw.get("booking"), raw.get("message")
        if raw.get("opted_out"):
            outcome, confidence = VerificationOutcome.opt_out, 1.0
        elif booking:
            outcome = VerificationOutcome.appointment_booked
            result["extracted"]["booking_uid"] = booking.get("uid")
            result["extracted"]["booked_for"] = booking.get("start")
            confidence = max(confidence, 0.99)
        elif message:
            outcome = VerificationOutcome.callback_needed
            result["extracted"]["callback_reason"] = message.get("reason")
            if message.get("details"):
                result["extracted"]["details"] = message.get("details")
            if message.get("callback_window"):
                result["extracted"]["callback_window"] = message.get("callback_window")
            confidence = max(confidence, 0.95)
        VERIFICATION_CONFIDENCE.observe(confidence)

        # Name the card from what the agent captured (an inbound caller has no pre-set name),
        # but only when the contact has none yet — so a known outbound contact's name still wins.
        captured_name = (booking or {}).get("name") or (message or {}).get("name")
        if captured_name:
            await db.execute(
                update(Contact)
                .where(Contact.id == sess.contact_id, Contact.customer_name.is_(None))
                .values(customer_name=captured_name)
            )

        # Transcript + recording (idempotent). Prefer the provider summary (free); else the
        # summary from the verify call — never a separate summarization request.
        existing = await db.scalar(select(Transcript).where(Transcript.call_session_id == sess.id))
        if existing is None:
            # Archive the transcript .txt to S3 (best-effort — never fail verify on S3, edge #27).
            text = "\n".join(f"[{t.get('role', '?')}] {t.get('text', '')}" for t in parsed.turns)
            transcript_key = await get_object_store().try_upload(
                f"transcripts/{sess.id}.txt", text.encode("utf-8"), content_type="text/plain"
            )
            db.add(
                Transcript(
                    call_session_id=sess.id,
                    turns=parsed.turns,
                    summary=parsed.summary or result.get("summary"),
                    s3_key=transcript_key,
                )
            )

        # Recording (idempotent, independent of the transcript): use an inline URL if the
        # provider supplied one, else fetch the audio out-of-band (ElevenLabs) and store it.
        rec_exists = await db.scalar(
            select(Recording).where(Recording.call_session_id == sess.id)
        )
        if rec_exists is None:
            rec_key = parsed.recording_url
            if rec_key is None:
                audio = await conversation.fetch_recording(parsed.provider_call_id)
                if audio:
                    rec_key = await get_object_store().try_upload(
                        f"recordings/{sess.id}.mp3", audio, content_type="audio/mpeg"
                    )
            if rec_key:
                db.add(
                    Recording(
                        call_session_id=sess.id,
                        s3_key=rec_key,
                        duration_s=parsed.duration_s,
                        uploaded=True,
                    )
                )
        if parsed.duration_s is not None:
            await advance_call_status(db, session_id=sess.id, new_status=CallStatus.completed)
            await db.execute(
                update(CallSession).where(CallSession.id == sess.id).values(duration_s=parsed.duration_s)
            )

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

        # Apply outcome to the contact; opt-out → suppress across ALL campaigns (edge #43).
        opted_out = outcome is VerificationOutcome.opt_out
        contact = await db.get(Contact, sess.contact_id)
        campaign = await db.get(Campaign, contact.campaign_id) if contact else None
        owner_id = campaign.owner_id if campaign else None
        await db.execute(
            update(Contact)
            .where(Contact.id == sess.contact_id)
            .values(
                status=ContactStatus.do_not_contact if opted_out else ContactStatus.completed,
                last_outcome=outcome.value,
                outcome_tags={"outcome": outcome.value, "confidence": confidence,
                              "extracted": result.get("extracted", {})},
            )
        )
        if opted_out and owner_id is not None and contact is not None:
            await suppress(db, owner_id, contact.phone_e164, reason="opt_out")

        # Accrue LLM spend; auto-pause the campaign at its ceiling (PRD §19.3).
        if campaign is not None and has_customer_speech:
            cost_micros = round(est_tokens / 1000 * settings.llm_cost_micros_per_1k_tokens)
            campaign.spent_micros = (campaign.spent_micros or 0) + cost_micros
            COST_MICROS.labels(campaign=str(campaign.id)).inc(cost_micros)
            if campaign.spend_ceiling_micros and campaign.spent_micros >= campaign.spend_ceiling_micros:
                campaign.status = CampaignStatus.paused
                log.warning("campaign_spend_ceiling_reached", campaign_id=str(campaign.id))

        await enqueue_outbox(
            db,
            aggregate_id=sess.id,
            event_type="call_verified",
            payload={"outcome": outcome.value, "confidence": confidence},
        )
        await db.commit()
        log.info("call_verified", outcome=outcome.value, confidence=confidence)

        # Push a live update so the dashboard feed updates in real time (PRD §18.1).
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
            on_start=get_object_store().ensure_bucket,
        )
    )


if __name__ == "__main__":
    main()
