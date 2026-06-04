"""Distributed token-bucket rate limiter, per provider (PRD §8.2).

Every external provider call passes through this. The bucket is sized below the
contracted limit with headroom. When empty, the dialer **re-queues with backoff** — it
never drops the contact. The refill+take is a single atomic Lua script so it holds
correctly across N worker replicas.
"""

from __future__ import annotations

import asyncio
import random
import time

from redis.asyncio import Redis

# Atomic token bucket: refill by elapsed time, take `cost` if available.
# Returns {allowed, wait_ms}.
_TOKEN_BUCKET_LUA = """
local key      = KEYS[1]
local rate     = tonumber(ARGV[1])     -- tokens per second
local capacity = tonumber(ARGV[2])     -- bucket size (burst)
local now      = tonumber(ARGV[3])     -- ms
local cost     = tonumber(ARGV[4])

local b = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(b[1])
local ts     = tonumber(b[2])
if tokens == nil then tokens = capacity; ts = now end

local delta = math.max(0, now - ts) / 1000.0
tokens = math.min(capacity, tokens + delta * rate)

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', key, 60000)

local wait = 0
if allowed == 0 then wait = math.ceil((cost - tokens) / rate * 1000) end
return {allowed, wait}
"""


class ProviderRateLimited(Exception):
    def __init__(self, provider: str, retry_after_ms: int) -> None:
        super().__init__(f"rate limited by {provider}, retry in {retry_after_ms}ms")
        self.provider = provider
        self.retry_after_ms = retry_after_ms


class ProviderRateLimiter:
    def __init__(self, redis: Redis, configs: dict[str, tuple[float, int]]) -> None:
        """configs: {provider: (tokens_per_sec, burst_capacity)}."""
        self._redis = redis
        self._configs = configs
        self._script = redis.register_script(_TOKEN_BUCKET_LUA)  # EVALSHA w/ fallback

    async def _eval(
        self, provider: str, rate: float, cap: int, cost: int
    ) -> tuple[int, int]:
        now_ms = int(time.time() * 1000)
        allowed, wait = await self._script(
            keys=[f"ratelimit:{provider}"], args=[rate, cap, now_ms, cost]
        )
        return int(allowed), int(wait)

    async def acquire(
        self, provider: str, cost: int = 1, max_wait_ms: int = 2000
    ) -> bool:
        """Block up to `max_wait_ms` for a token; raise ProviderRateLimited if none frees."""
        if provider not in self._configs:
            return True  # no configured bucket (e.g. the mock provider) → unrestricted
        rate, cap = self._configs[provider]
        deadline = time.monotonic() + max_wait_ms / 1000
        while True:
            allowed, wait = await self._eval(provider, rate, cap, cost)
            if allowed:
                return True
            if time.monotonic() >= deadline:
                raise ProviderRateLimited(provider, retry_after_ms=wait)
            await asyncio.sleep(min(wait, 100) / 1000 + random.uniform(0, 0.05))
