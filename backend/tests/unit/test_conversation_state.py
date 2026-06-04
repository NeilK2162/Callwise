"""Per-session conversation state — disjoint keys, checkpoint TTL (PRD §7.2)."""

from __future__ import annotations

import uuid

from callwise.domain.state import (
    ConversationState,
    checkpoint_state,
    clear_state,
    load_state,
)


async def test_checkpoint_and_load_roundtrip(redis_client):
    sid = uuid.uuid4()
    state = ConversationState(
        call_session_id=sid,
        fsm_node="collect_name",
        collected_slots={"name": "Priya"},
        turn_count=2,
    )
    await checkpoint_state(redis_client, state, ttl=120)
    loaded = await load_state(redis_client, sid)
    assert loaded is not None
    assert loaded.fsm_node == "collect_name"
    assert loaded.collected_slots["name"] == "Priya"
    assert loaded.turn_count == 2


async def test_sessions_are_isolated(redis_client):
    a, b = uuid.uuid4(), uuid.uuid4()
    await checkpoint_state(
        redis_client,
        ConversationState(call_session_id=a, fsm_node="a"),
        ttl=120,
    )
    await checkpoint_state(
        redis_client,
        ConversationState(call_session_id=b, fsm_node="b"),
        ttl=120,
    )
    assert (await load_state(redis_client, a)).fsm_node == "a"
    assert (await load_state(redis_client, b)).fsm_node == "b"


async def test_clear_removes_state(redis_client):
    sid = uuid.uuid4()
    await checkpoint_state(
        redis_client, ConversationState(call_session_id=sid), ttl=60
    )
    await clear_state(redis_client, sid)
    assert await load_state(redis_client, sid) is None


async def test_missing_session_returns_none(redis_client):
    assert await load_state(redis_client, uuid.uuid4()) is None
