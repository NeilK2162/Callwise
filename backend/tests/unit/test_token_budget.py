"""LLM token-budget (TPM) limiter — queues under surge, never overruns (PRD §19.3)."""

import pytest

from callwise.governors.token_budget import TokenBudgetExceeded, TokenBudgetLimiter


async def test_allows_within_budget(redis_client):
    limiter = TokenBudgetLimiter(redis_client, tokens_per_minute=60_000, key="test:tpm:ok")
    assert await limiter.acquire(1000) is True


async def test_exhausts_then_raises(redis_client):
    # 600 tokens/min budget == capacity 600, refill 10/sec.
    limiter = TokenBudgetLimiter(redis_client, tokens_per_minute=600, key="test:tpm:drain")
    assert await limiter.acquire(600) is True  # drains the bucket
    with pytest.raises(TokenBudgetExceeded):
        await limiter.acquire(600, max_wait_ms=50)  # refill can't cover 600 in 50ms


async def test_request_capped_to_bucket_size(redis_client):
    # Requesting more than the whole bucket is clamped, not deadlocked.
    limiter = TokenBudgetLimiter(redis_client, tokens_per_minute=1000, key="test:tpm:cap")
    assert await limiter.acquire(50_000) is True
