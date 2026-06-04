"""Cross-campaign do-not-contact suppression (PRD §14.2, edge cases #42, #43).

A number suppressed for an owner is never dialed again across any of their campaigns. The
agent's opt-out action and the post-call `opt_out` outcome both write here.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from callwise.db.models import Suppression


async def is_suppressed(db: AsyncSession, owner_id: uuid.UUID, phone_e164: str) -> bool:
    found = await db.scalar(
        select(Suppression.id).where(
            Suppression.owner_id == owner_id, Suppression.phone_e164 == phone_e164
        )
    )
    return found is not None


async def suppress(
    db: AsyncSession, owner_id: uuid.UUID, phone_e164: str, *, reason: str = "opt_out"
) -> None:
    """Idempotent add to the suppression list (no-op if already present)."""
    stmt = (
        pg_insert(Suppression)
        .values(owner_id=owner_id, phone_e164=phone_e164, reason=reason)
        .on_conflict_do_nothing(constraint="uq_suppression_owner_phone")
    )
    await db.execute(stmt)
