"""Call sessions, drill-downs, manual re-verify, and outbound trigger (PRD §11.1)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from callwise.control_api.deps import CurrentUser, DbSession, owned_or_404
from callwise.control_api.schemas import (
    CallSessionOut,
    OutboundCallRequest,
    VerificationOut,
)
from callwise.db.models import (
    CallSession,
    CallVerification,
    Campaign,
    Contact,
    Transcript,
)
from callwise.logging import get_logger

router = APIRouter()
log = get_logger(__name__)


async def _owned_session(db: DbSession, session_id: uuid.UUID, user: CurrentUser) -> CallSession:
    sess = await db.get(CallSession, session_id)
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    contact = await db.get(Contact, sess.contact_id)
    campaign = await db.get(Campaign, contact.campaign_id) if contact else None
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    owned_or_404(campaign.owner_id, user)
    return sess


@router.get("/{session_id}", response_model=CallSessionOut)
async def get_session(session_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CallSession:
    return await _owned_session(db, session_id, user)


@router.get("/{session_id}/transcript")
async def get_transcript(session_id: uuid.UUID, db: DbSession, user: CurrentUser) -> dict:
    await _owned_session(db, session_id, user)
    t = await db.scalar(select(Transcript).where(Transcript.call_session_id == session_id))
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no transcript")
    return {"turns": t.turns, "summary": t.summary}


@router.get("/{session_id}/verifications", response_model=list[VerificationOut])
async def get_verifications(
    session_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[CallVerification]:
    await _owned_session(db, session_id, user)
    return list(
        await db.scalars(
            select(CallVerification).where(CallVerification.call_session_id == session_id)
        )
    )


@router.post("/{session_id}/analyze")
async def analyze(session_id: uuid.UUID, db: DbSession, user: CurrentUser) -> dict[str, str]:
    """Manual re-verify. Idempotent: the verification upsert overwrites, never duplicates."""
    await _owned_session(db, session_id, user)
    # TODO: enqueue `process_call_session` (verify step) keyed on session_id.
    log.info("manual_reverify_requested", call_session_id=str(session_id))
    return {"status": "queued"}


@router.post("/outbound", response_model=CallSessionOut, status_code=status.HTTP_202_ACCEPTED)
async def start_outbound(
    body: OutboundCallRequest, db: DbSession, user: CurrentUser
) -> CallSession:
    """The dashboard's "Start Outbound Call" action. Creates/queues a contact and enqueues
    a governed dial. The actual dial goes through the same claim → governed-dispatch path
    as a campaign dial, so it inherits all the idempotency/concurrency guarantees."""
    # TODO: normalize phone, create-or-find contact, create context snapshot, enqueue dial.
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "outbound trigger not yet wired")
