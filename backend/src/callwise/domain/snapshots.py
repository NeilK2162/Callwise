"""Immutable per-session context snapshots (PRD §7.1).

At dial time we freeze the contact's data + the agent config *as it was at launch*. If an
operator edits the prompt or the contact mid-campaign, in-flight calls keep the version
they started with. The snapshot is **never updated** — corrections create a new snapshot
for the next attempt. The conversation layer fetches it by `call_session_id`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from callwise.db.models import ContextSnapshot


@dataclass(frozen=True)
class CallContextSnapshot:
    snapshot_id: uuid.UUID
    contact_id: uuid.UUID
    # Frozen contact data
    customer_name: str | None
    phone_e164: str
    language: str
    custom_fields: dict
    # Frozen agent config
    agent_id: str | None
    prompt_version: str | None
    script_flow_id: str | None
    dynamic_variables: dict
    # Guardrails
    max_call_duration_s: int
    allowed_actions: list[str]
    created_at: datetime = field(default_factory=datetime.utcnow)


async def create_snapshot(
    session: AsyncSession,
    *,
    contact_id: uuid.UUID,
    customer_name: str | None,
    phone_e164: str,
    language: str,
    custom_fields: dict,
    agent_id: str | None,
    prompt_version: str | None = None,
    script_flow_id: str | None = None,
    dynamic_variables: dict | None = None,
    max_call_duration_s: int = 300,
    allowed_actions: list[str] | None = None,
) -> ContextSnapshot:
    snap = ContextSnapshot(
        contact_id=contact_id,
        customer_name=customer_name,
        phone_e164=phone_e164,
        language=language,
        custom_fields=custom_fields,
        agent_id=agent_id,
        prompt_version=prompt_version,
        script_flow_id=script_flow_id,
        dynamic_variables=dynamic_variables or {},
        max_call_duration_s=max_call_duration_s,
        allowed_actions=allowed_actions or ["end_call"],
    )
    session.add(snap)
    await session.flush()
    return snap


async def load_snapshot(
    session: AsyncSession, snapshot_id: uuid.UUID
) -> CallContextSnapshot | None:
    row = await session.scalar(
        select(ContextSnapshot).where(ContextSnapshot.id == snapshot_id)
    )
    if row is None:
        return None
    return CallContextSnapshot(
        snapshot_id=row.id,
        contact_id=row.contact_id,
        customer_name=row.customer_name,
        phone_e164=row.phone_e164,
        language=row.language,
        custom_fields=row.custom_fields,
        agent_id=row.agent_id,
        prompt_version=row.prompt_version,
        script_flow_id=row.script_flow_id,
        dynamic_variables=row.dynamic_variables,
        max_call_duration_s=row.max_call_duration_s,
        allowed_actions=row.allowed_actions,
        created_at=row.created_at,
    )
