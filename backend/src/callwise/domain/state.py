"""Mutable per-session conversation state (PRD §7.2).

Only the LiveKit real-time path owns turn-by-turn state (the ElevenLabs ConvAI path lets
the provider hold it). State is keyed strictly by `call_session_id` and checkpointed to
Redis after every transition, so a worker restart recovers an active call's slot-fill
progress.

Isolation guarantee: the keyspace is physically disjoint per session
(`convstate:{call_session_id}`), so two of N concurrent calls cannot read or write each
other's state. There is no shared mutable structure across sessions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from redis.asyncio import Redis


class ConversationState(BaseModel):
    call_session_id: uuid.UUID
    fsm_node: str = "start"
    collected_slots: dict[str, Any] = Field(default_factory=dict)
    turn_count: int = 0
    last_customer_utterance: str | None = None
    reprompt_count: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def _key(call_session_id: uuid.UUID) -> str:
    return f"convstate:{call_session_id}"


async def checkpoint_state(redis: Redis, state: ConversationState, *, ttl: int) -> None:
    """Persist after every state transition. TTL = max_call_duration + buffer."""
    await redis.set(_key(state.call_session_id), state.model_dump_json(), ex=ttl)


async def load_state(
    redis: Redis, call_session_id: uuid.UUID
) -> ConversationState | None:
    raw = await redis.get(_key(call_session_id))
    if raw is None:
        return None
    return ConversationState.model_validate_json(raw)


async def clear_state(redis: Redis, call_session_id: uuid.UUID) -> None:
    await redis.delete(_key(call_session_id))
