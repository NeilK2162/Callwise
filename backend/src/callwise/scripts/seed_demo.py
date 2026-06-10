"""Seed a demo clinic dashboard (PRD §0.6: "2–3 pre-seeded example calls").

Creates a demo user, a dental-clinic campaign, and a handful of completed calls with
transcripts + verifications, so `/api/reports/feed` returns live query cards on first run.

    uv run python -m callwise.scripts.seed_demo

Login: demo@callwise.dev / demo12345
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from callwise.control_api.security import hash_password
from callwise.db.base import get_sessionmaker
from callwise.db.enums import CallDirection, CallStatus, ContactStatus, VerificationOutcome
from callwise.db.models import (
    CallSession,
    CallVerification,
    Campaign,
    Contact,
    Recording,
    Transcript,
    User,
)
from callwise.logging import configure_logging, get_logger

log = get_logger(__name__)

_DEMO = [
    {
        "name": "Priya Sharma",
        "phone": "+13853962012",
        "direction": CallDirection.inbound,
        "outcome": VerificationOutcome.appointment_booked,
        "summary": "Asked about root canal cost and earliest Saturday slot. "
        "Booked for Sat 11 AM. Confirmed via SMS.",
        "extracted": {"name": "Priya", "service": "root canal", "date": "Sat 11AM"},
        "duration_s": 132,
    },
    {
        "name": "Rahul Verma",
        "phone": "+14158675309",
        "direction": CallDirection.inbound,
        "outcome": VerificationOutcome.callback_needed,
        "summary": "Wanted to reschedule a cleaning but preferred slot was full. "
        "Asked for a callback tomorrow morning.",
        "extracted": {"name": "Rahul", "intent": "reschedule"},
        "duration_s": 74,
    },
    {
        "name": "Aisha Khan",
        "phone": "+12025551234",
        "direction": CallDirection.outbound,
        "outcome": VerificationOutcome.question_answered,
        "summary": "Appointment reminder for Friday 4 PM. Confirmed attendance.",
        "extracted": {"name": "Aisha", "confirmed": True},
        "duration_s": 41,
    },
]


async def seed() -> None:
    configure_logging("INFO", json=False)
    async with get_sessionmaker()() as db:
        existing = await db.scalar(select(User).where(User.email == "demo@callwise.dev"))
        if existing is not None:
            log.info("already_seeded", user=str(existing.id))
            return

        user = User(
            email="demo@callwise.dev",
            password_hash=hash_password("demo12345"),
        )
        db.add(user)
        await db.flush()

        campaign = Campaign(
            owner_id=user.id, name="Bright Smile Dental", provider="mock", agent_id="clinic-v1"
        )
        db.add(campaign)
        await db.flush()

        now = datetime.now(UTC)
        for i, row in enumerate(_DEMO):
            contact = Contact(
                campaign_id=campaign.id,
                phone_e164=row["phone"],
                customer_name=row["name"],
                status=ContactStatus.completed,
                attempt_count=1,
                last_outcome=row["outcome"].value,
            )
            db.add(contact)
            await db.flush()

            session_id = uuid.uuid4()
            db.add(
                CallSession(
                    id=session_id,
                    contact_id=contact.id,
                    direction=row["direction"],
                    provider="mock",
                    provider_call_id=f"mock-{session_id}",
                    status=CallStatus.completed,
                    started_at=now - timedelta(minutes=15 * (i + 1)),
                    ended_at=now - timedelta(minutes=15 * (i + 1)) + timedelta(seconds=row["duration_s"]),
                    duration_s=row["duration_s"],
                    end_reason="hangup_customer",
                )
            )
            db.add(
                Transcript(
                    call_session_id=session_id,
                    summary=row["summary"],
                    turns=[
                        {"role": "agent", "text": "Thanks for calling Bright Smile Dental!", "ts": 0},
                        {"role": "customer", "text": "Hi, I had a question.", "ts": 3},
                    ],
                )
            )
            db.add(
                CallVerification(
                    call_session_id=session_id,
                    step="verify",
                    outcome=row["outcome"],
                    responder_type="human",
                    confidence=0.93,
                    extracted=row["extracted"],
                    result={"outcome": row["outcome"].value},
                )
            )
            # No Recording row: seed calls are synthetic, there is no real audio to play. The
            # card shows "No recording available" — honest. Real calls store a fetched recording.

        await db.commit()
        log.info("seeded", user="demo@callwise.dev", calls=len(_DEMO))


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
