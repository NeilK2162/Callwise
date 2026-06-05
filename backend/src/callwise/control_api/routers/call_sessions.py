"""Call sessions, drill-downs, manual re-verify, and outbound trigger (PRD §11.1)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from callwise.control_api.deps import CurrentUser, DbSession, owned_or_404
from callwise.control_api.schemas import (
    CallSessionOut,
    OutboundAck,
    OutboundCallRequest,
    VerificationOut,
)
from callwise.config import get_settings
from callwise.db.enums import CallDirection, CampaignStatus, ContactStatus
from callwise.db.models import (
    CallSession,
    CallVerification,
    Campaign,
    Contact,
    Recording,
    Transcript,
)
from callwise.domain.phone import InvalidPhoneNumber, normalize_e164
from callwise.logging import get_logger
from callwise.orchestration import enqueue_single_dial
from callwise.queue.factory import get_queue
from callwise.storage import get_object_store

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


@router.get("/{session_id}/recording")
async def session_recording(
    session_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> dict[str, str]:
    """Presigned playback URL for the call's recording (PRD §14.5)."""
    await _owned_session(db, session_id, user)
    rec = await db.scalar(
        select(Recording).where(
            Recording.call_session_id == session_id, Recording.uploaded.is_(True)
        )
    )
    if rec is None or rec.s3_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no recording")
    key = rec.s3_key
    if key.startswith(("mock://", "s3://", "http://", "https://")):
        url = key  # demo/local placeholder or already-public URL
    else:
        url = await get_object_store().presigned_get(key, expires=300)
    return {"url": url}


@router.post("/{session_id}/analyze")
async def analyze(session_id: uuid.UUID, db: DbSession, user: CurrentUser) -> dict[str, str]:
    """Manual re-verify. Enqueues a re-verify task; the upsert overwrites, never duplicates."""
    await _owned_session(db, session_id, user)
    await get_queue().publish(
        get_settings().verify_stream,
        {"provider": "reverify", "call_session_id": str(session_id)},
        idempotency_key=f"reverify:{session_id}",
    )
    log.info("manual_reverify_requested", call_session_id=str(session_id))
    return {"status": "queued"}


@router.post("/outbound", response_model=OutboundAck, status_code=status.HTTP_202_ACCEPTED)
async def start_outbound(
    body: OutboundCallRequest, db: DbSession, user: CurrentUser
) -> OutboundAck:
    """The dashboard's "Start Outbound Call" action. Queues a contact and enqueues a
    governed dial through the SAME claim → governed-dispatch path as a campaign dial, so it
    inherits every idempotency/concurrency guarantee."""
    try:
        phone = normalize_e164(body.phone, "IN")
    except InvalidPhoneNumber as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid phone number") from exc

    if body.campaign_id is not None:
        campaign = await db.get(Campaign, body.campaign_id)
        if campaign is None or (not user.is_superuser and campaign.owner_id != user.id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    else:
        # Find or create the user's ad-hoc outbound campaign.
        campaign = await db.scalar(
            select(Campaign).where(
                Campaign.owner_id == user.id, Campaign.name == "Outbound (ad-hoc)"
            )
        )
        if campaign is None:
            campaign = Campaign(
                owner_id=user.id,
                name="Outbound (ad-hoc)",
                provider="mock",
                direction=CallDirection.outbound,
                status=CampaignStatus.running,
            )
            db.add(campaign)
            await db.flush()

    contact = Contact(
        campaign_id=campaign.id,
        phone_e164=phone,
        customer_name=body.customer_name,
        status=ContactStatus.queued,
    )
    db.add(contact)
    await db.commit()

    await enqueue_single_dial(get_queue(), campaign_id=campaign.id, contact_id=contact.id)
    log.info("outbound_enqueued", contact_id=str(contact.id), campaign_id=str(campaign.id))
    return OutboundAck(status="queued", contact_id=contact.id, campaign_id=campaign.id)
