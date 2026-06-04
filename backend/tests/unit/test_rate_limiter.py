"""Token-bucket rate limiter — atomic take, backoff when empty (PRD §8.2)."""

from __future__ import annotations

import pytest

from callwise.governors.rate_limiter import ProviderRateLimited, ProviderRateLimiter


async def test_unconfigured_provider_is_unrestricted(redis_client):
    limiter = ProviderRateLimiter(redis_client, configs={})
    assert await limiter.acquire("mock", cost=1, max_wait_ms=0) is True


async def test_burst_then_rate_limit(redis_client):
    # 10 tokens/sec, burst 2 — third immediate acquire should fail.
    limiter = ProviderRateLimiter(
        redis_client, configs={"exotel": (10.0, 2)}
    )
    assert await limiter.acquire("exotel", cost=1, max_wait_ms=0)
    assert await limiter.acquire("exotel", cost=1, max_wait_ms=0)
    with pytest.raises(ProviderRateLimited) as exc:
        await limiter.acquire("exotel", cost=1, max_wait_ms=0)
    assert exc.value.provider == "exotel"
    assert exc.value.retry_after_ms >= 0


async def test_tokens_refill_over_time(redis_client):
    limiter = ProviderRateLimiter(
        redis_client, configs={"twilio": (100.0, 1)}
    )
    assert await limiter.acquire("twilio", cost=1, max_wait_ms=0)
    with pytest.raises(ProviderRateLimited):
        await limiter.acquire("twilio", cost=1, max_wait_ms=0)
    # Wait for refill (~10ms at 100/s for 1 token).
    assert await limiter.acquire("twilio", cost=1, max_wait_ms=500)
