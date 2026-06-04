"""Global concurrency governor — the live-call ceiling (PRD §8.3).

Caps simultaneous live calls per scope (campaign and/or global), independent of how fast
the queue drains. Implemented as a Redis **sorted set scored by lease expiry**, not a
plain counter: an INCR/DECR counter leaks a slot forever if a worker crashes between
INCR and DECR, whereas expired members in a ZSET get pruned, so the live-call count is
always *eventually accurate* and self-heals.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

# Prune expired holders, then add this token iff under the limit. Atomic.
# Returns 1 if the slot was acquired, 0 otherwise.
_ACQUIRE_LUA = """
local key   = KEYS[1]
local now   = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local token = ARGV[3]
local expiry = tonumber(ARGV[4])

redis.call('ZREMRANGEBYSCORE', key, 0, now)     -- prune dead holders
local used = redis.call('ZCARD', key)
if used < limit then
  redis.call('ZADD', key, expiry, token)
  redis.call('PEXPIRE', key, 600000)
  return 1
end
return 0
"""


class ConcurrencyLimitReached(Exception):
    def __init__(self, scope: str) -> None:
        super().__init__(f"concurrency limit reached for {scope}")
        self.scope = scope


class ConcurrencyGovernor:
    """Distributed semaphore with self-healing leases."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._acquire = redis.register_script(_ACQUIRE_LUA)

    async def _try_acquire(
        self, key: str, token: str, limit: int, now: float, lease_ttl: int
    ) -> bool:
        result = await self._acquire(
            keys=[key], args=[now, limit, token, now + lease_ttl]
        )
        return bool(result)

    @asynccontextmanager
    async def slot(
        self, scope: str, limit: int, lease_ttl: int = 180
    ) -> AsyncIterator[str]:
        """Hold a live-call slot for `scope`. Released on exit; reclaimed via lease on crash."""
        token = str(uuid.uuid4())
        key = f"concgov:{scope}"
        now = time.time()
        if not await self._try_acquire(key, token, limit, now, lease_ttl):
            raise ConcurrencyLimitReached(scope)
        try:
            yield token
        finally:
            await self._redis.zrem(key, token)

    async def in_use(self, scope: str) -> int:
        """Current live count for a scope (prunes expired first)."""
        key = f"concgov:{scope}"
        await self._redis.zremrangebyscore(key, 0, time.time())
        return await self._redis.zcard(key)
