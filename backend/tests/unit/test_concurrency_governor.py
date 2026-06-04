"""Concurrency governor — ZSET leases, no slot leaks (PRD §8.3)."""

from __future__ import annotations

import time
import uuid

import pytest

from callwise.governors.concurrency import ConcurrencyGovernor, ConcurrencyLimitReached


async def test_acquire_up_to_limit_then_reject(redis_client):
    gov = ConcurrencyGovernor(redis_client)
    scope = "test-campaign"
    async with gov.slot(scope, limit=2, lease_ttl=60):
        async with gov.slot(scope, limit=2, lease_ttl=60):
            with pytest.raises(ConcurrencyLimitReached):
                async with gov.slot(scope, limit=2, lease_ttl=60):
                    pass  # pragma: no cover


async def test_slot_released_after_context_exit(redis_client):
    gov = ConcurrencyGovernor(redis_client)
    scope = "release-test"
    async with gov.slot(scope, limit=1, lease_ttl=60):
        pass
    async with gov.slot(scope, limit=1, lease_ttl=60) as token:
        assert token


async def test_expired_lease_self_heals_slot(redis_client):
    """Simulate a worker crash: token left in ZSET with past expiry score."""
    gov = ConcurrencyGovernor(redis_client)
    scope = "lease-heal"
    key = f"concgov:{scope}"
    await redis_client.zadd(key, {str(uuid.uuid4()): time.time() - 10})
    assert await gov.in_use(scope) == 0
    async with gov.slot(scope, limit=1, lease_ttl=60):
        assert await gov.in_use(scope) == 1


async def test_in_use_counts_active_holders(redis_client):
    gov = ConcurrencyGovernor(redis_client)
    scope = "count"
    assert await gov.in_use(scope) == 0
    async with gov.slot(scope, limit=3, lease_ttl=60):
        assert await gov.in_use(scope) == 1
        async with gov.slot(scope, limit=3, lease_ttl=60):
            assert await gov.in_use(scope) == 2
