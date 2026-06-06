"""Shared fixtures — Redis-backed tests skip when no broker is reachable."""

from __future__ import annotations

import os

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError


def _redis_url() -> str:
    return os.getenv("CALLWISE_TEST_REDIS_URL", "redis://127.0.0.1:6379/15")


@pytest.fixture
async def redis_client() -> Redis:
    """Isolated Redis DB (default 15). Skips (not errors) when no broker is reachable —
    redis-py raises redis.exceptions.ConnectionError, which is NOT an OSError subclass."""
    client: Redis = Redis.from_url(_redis_url(), decode_responses=True)
    try:
        if not await client.ping():
            pytest.skip("Redis ping failed")
    except (RedisError, OSError):
        pytest.skip("Redis not available for governor/state tests")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
