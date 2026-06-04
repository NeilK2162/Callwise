"""Redis distributed lock (Redlock-lite) with TTL auto-release (PRD §6.4, §12.3).

A single-instance lock via `SET key token NX PX ttl`. The TTL guarantees a crashed holder
can't deadlock the system — the lock auto-releases. Release is a compare-and-delete Lua so
we only delete a lock we still own (never another holder's after our TTL lapsed).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


@asynccontextmanager
async def redlock(
    redis: Redis, key: str, *, ttl_ms: int = 30_000
) -> AsyncIterator[bool]:
    """Yield True if the lock was acquired, False otherwise. Always releases what it owns."""
    token = str(uuid.uuid4())
    acquired = bool(await redis.set(f"lock:{key}", token, nx=True, px=ttl_ms))
    try:
        yield acquired
    finally:
        if acquired:
            await redis.eval(_RELEASE_LUA, 1, f"lock:{key}", token)
