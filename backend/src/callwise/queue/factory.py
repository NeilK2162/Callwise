"""Queue factory — returns the configured broker (Redis Streams default, SQS path)."""

from __future__ import annotations

from functools import lru_cache

from callwise.config import get_settings
from callwise.queue.base import Queue
from callwise.queue.redis_streams import RedisStreamsQueue
from callwise.redis_pool import get_redis


@lru_cache
def get_queue() -> Queue:
    s = get_settings()
    return RedisStreamsQueue(
        get_redis(), dlq_stream=s.dlq_stream, max_attempts=s.queue_max_attempts
    )
