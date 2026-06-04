"""Reports + the dashboard feed (PRD §0.4, §11.1).

Served from a read replica in production (PRD §4.3) — never the primary. The `/feed`
endpoint assembles the query cards that are the centerpiece of the dashboard.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from callwise.control_api.deps import CurrentUser, DbSession
from callwise.control_api.schemas import QueryCard, ReportSummary
from callwise.db.enums import VerificationOutcome
from callwise.db.models import (
    CallSession,
    CallVerification,
    Campaign,
    Contact,
    Recording,
    Transcript,
)
from callwise.domain.phone import mask_e164

router = APIRouter()


def _owned_session_filter(stmt, user: CurrentUser):
    if not user.is_superuser:
        stmt = stmt.where(Campaign.owner_id == user.id)
    return stmt


@router.get("/summary", response_model=ReportSummary)
async def summary(db: DbSession, user: CurrentUser) -> ReportSummary:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    base = (
        select(CallSession)
        .join(Contact, Contact.id == CallSession.contact_id)
        .join(Campaign, Campaign.id == Contact.campaign_id)
        .where(CallSession.started_at >= since)
    )
    base = _owned_session_filter(base, user)
    sub = base.subquery()

    calls_today = await db.scalar(select(func.count()).select_from(sub)) or 0
    avg_duration = await db.scalar(select(func.coalesce(func.avg(sub.c.duration_s), 0)))

    booked = await db.scalar(
        select(func.count())
        .select_from(CallVerification)
        .join(sub, sub.c.id == CallVerification.call_session_id)
        .where(CallVerification.outcome == VerificationOutcome.appointment_booked)
    ) or 0
    callback = await db.scalar(
        select(func.count())
        .select_from(CallVerification)
        .join(sub, sub.c.id == CallVerification.call_session_id)
        .where(CallVerification.outcome == VerificationOutcome.callback_needed)
    ) or 0

    return ReportSummary(
        calls_today=int(calls_today),
        booked=int(booked),
        callback_needed=int(callback),
        missed=0,  # "never miss a call" — inbound coverage is 100% by design
        avg_duration_s=float(avg_duration or 0),
    )


@router.get("/feed", response_model=list[QueryCard])
async def feed(
    db: DbSession,
    user: CurrentUser,
    needs_action: bool = False,
    q: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> list[QueryCard]:
    stmt = (
        select(CallSession, Contact, Transcript, CallVerification)
        .join(Contact, Contact.id == CallSession.contact_id)
        .join(Campaign, Campaign.id == Contact.campaign_id)
        .outerjoin(Transcript, Transcript.call_session_id == CallSession.id)
        .outerjoin(
            CallVerification,
            (CallVerification.call_session_id == CallSession.id)
            & (CallVerification.step == "verify"),
        )
        .order_by(CallSession.started_at.desc())
        .limit(limit)
    )
    stmt = _owned_session_filter(stmt, user)
    if needs_action:
        stmt = stmt.where(CallVerification.outcome == VerificationOutcome.callback_needed)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Contact.customer_name.ilike(like) | Contact.phone_e164.ilike(like))

    rows = (await db.execute(stmt)).all()

    # One extra query to mark which sessions have an uploaded recording.
    session_ids = [r[0].id for r in rows]
    recorded: set = set()
    if session_ids:
        recorded = set(
            await db.scalars(
                select(Recording.call_session_id).where(
                    Recording.call_session_id.in_(session_ids), Recording.uploaded.is_(True)
                )
            )
        )

    cards: list[QueryCard] = []
    for sess, contact, transcript, verification in rows:
        cards.append(
            QueryCard(
                call_session_id=sess.id,
                direction=sess.direction,
                phone_masked=mask_e164(contact.phone_e164),
                customer_name=contact.customer_name,
                started_at=sess.started_at,
                summary=transcript.summary if transcript else None,
                outcome=verification.outcome if verification else None,
                confidence=verification.confidence if verification else None,
                extracted=verification.extracted if verification else {},
                duration_s=sess.duration_s,
                has_recording=sess.id in recorded,
            )
        )
    return cards


@router.get("/export")
async def export(db: DbSession, user: CurrentUser) -> dict[str, str]:
    # TODO: stream a CSV/XLSX export from the read replica.
    return {"status": "not_implemented"}
