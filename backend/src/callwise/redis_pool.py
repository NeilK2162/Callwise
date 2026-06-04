"""Shared async Redis client.

One connection pool per process (Redis Cluster + AOF in prod, PRD §15.1). Used by the
governors, the broker, and per-session conversation state. Locks carry TTLs so a crashed
holder auto-releases (PRD §12.3 edge #31).
"""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis

from callwise.config import get_settings


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(
        get_settings().redis_url, encoding="utf-8", decode_responses=False
    )
