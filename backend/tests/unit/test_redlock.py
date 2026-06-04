"""Distributed lock — NX acquire, token-safe release (PRD §6.4)."""

from __future__ import annotations

import uuid

import pytest
from redis.asyncio import Redis

from callwise.locks import redlock


async def test_only_one_holder_wins(redis_client: Redis):
    key = "campaign-start"
    async with redlock(redis_client, key, ttl_ms=5000) as first:
        assert first is True
        async with redlock(redis_client, key, ttl_ms=5000) as second:
            assert second is False


async def test_release_frees_lock_for_next_acquirer(redis_client: Redis):
    key = "campaign-start-2"
    async with redlock(redis_client, key, ttl_ms=5000) as acquired:
        assert acquired is True
    async with redlock(redis_client, key, ttl_ms=5000) as again:
        assert again is True


async def test_wrong_token_cannot_steal_release(redis_client: Redis):
    key = "campaign-start-3"
    lock_key = f"lock:{key}"
    await redis_client.set(lock_key, "other-holders-token", px=5000)
    async with redlock(redis_client, key, ttl_ms=5000) as acquired:
        assert acquired is False
    assert await redis_client.get(lock_key) == "other-holders-token"


async def test_set_nx_race_exactly_one_wins(redis_client: Redis):
    """Raw SET NX race — the primitive redlock relies on."""
    lock_key = "lock:race"
    results: list[bool] = []
    for _ in range(8):
        token = str(uuid.uuid4())
        results.append(
            bool(await redis_client.set(lock_key, token, nx=True, px=5000))
        )
    assert results.count(True) == 1
    assert results.count(False) == 7
