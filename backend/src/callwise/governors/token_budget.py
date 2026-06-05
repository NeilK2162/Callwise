"""LLM token-budget limiter — tokens/minute (PRD §8.4, §19.3).

A distributed token bucket keyed on *tokens* (not requests). Verification workers acquire
an estimated token cost before each LLM call; when the per-minute budget is exhausted the
call **waits** (verification isn't latency-critical to the second) and only raises after a
bounded wait — so a surge queues instead of blowing the deployment's TPM quota or spiking
spend. Reuses the same atomic refill+take Lua as the per-provider dial limiter.
"""

from __future__ import annotations

import asyncio
import random
import time

from redis.asyncio import Redis

from callwise.governors.rate_limiter import _TOKEN_BUCKET_LUA


class TokenBudgetExceeded(Exception):
    def __init__(self, retry_after_ms: int) -> None:
        super().__init__(f"LLM token budget exhausted, retry in {retry_after_ms}ms")
        self.retry_after_ms = retry_after_ms


class TokenBudgetLimiter:
    def __init__(self, redis: Redis, tokens_per_minute: int, *, key: str = "llm:tpm") -> None:
        self._redis = redis
        self._rate = tokens_per_minute / 60.0  # tokens per second
        self._capacity = max(tokens_per_minute, 1)  # 1-minute burst
        self._key = key
        self._script = redis.register_script(_TOKEN_BUCKET_LUA)

    async def acquire(self, tokens: int, *, max_wait_ms: int = 3000) -> bool:
        """Block up to max_wait_ms for `tokens` of budget; raise TokenBudgetExceeded if none."""
        cost = min(tokens, self._capacity)  # never request more than the whole bucket
        deadline = time.monotonic() + max_wait_ms / 1000
        while True:
            now_ms = int(time.time() * 1000)
            allowed, wait = await self._script(
                keys=[self._key], args=[self._rate, self._capacity, now_ms, cost]
            )
            if int(allowed):
                return True
            if time.monotonic() >= deadline:
                raise TokenBudgetExceeded(retry_after_ms=int(wait))
            await asyncio.sleep(min(int(wait), 200) / 1000 + random.uniform(0, 0.05))
