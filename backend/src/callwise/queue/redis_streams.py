"""Redis Streams + consumer groups broker (PRD §8.1, default).

The Pending Entries List (PEL) gives at-least-once with explicit ACK. A crashed worker's
in-flight messages are recovered by `XAUTOCLAIM` past an idle threshold. A message that
exceeds `max_attempts` is moved to the DLQ and ACKed off the main stream so it never
blocks the queue head (PRD §9.4).
"""

from __future__ import annotations

from typing import Any

import orjson
from redis.asyncio import Redis

from callwise.logging import get_logger
from callwise.queue.base import Message, Queue

log = get_logger(__name__)


class RedisStreamsQueue(Queue):
    def __init__(self, redis: Redis, *, dlq_stream: str, max_attempts: int = 5) -> None:
        self._redis = redis
        self._dlq_stream = dlq_stream
        self._max_attempts = max_attempts

    async def ensure_group(self, stream: str, group: str) -> None:
        try:
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception as exc:  # noqa: BLE001
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish(
        self, stream: str, payload: dict[str, Any], *, idempotency_key: str | None = None
    ) -> str:
        fields = {
            b"data": orjson.dumps(payload),
            b"attempts": b"1",
        }
        if idempotency_key:
            fields[b"idem"] = idempotency_key.encode()
        return await self._redis.xadd(stream, fields)

    def _to_message(self, stream: str, msg_id: Any, fields: dict[Any, Any]) -> Message:
        data = fields.get(b"data") or fields.get("data") or b"{}"
        idem = fields.get(b"idem") or fields.get("idem")
        attempts = fields.get(b"attempts") or fields.get("attempts") or b"1"
        mid = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
        return Message(
            id=mid,
            stream=stream,
            payload=orjson.loads(data),
            idempotency_key=idem.decode() if isinstance(idem, bytes) else idem,
            attempts=int(attempts),
        )

    async def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        count: int = 10,
        block_ms: int = 2000,
    ) -> list[Message]:
        resp = await self._redis.xreadgroup(
            group, consumer, {stream: ">"}, count=count, block=block_ms
        )
        if not resp:
            return []
        out: list[Message] = []
        for _stream, entries in resp:
            for msg_id, fields in entries:
                out.append(self._to_message(stream, msg_id, fields))
        return out

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        await self._redis.xack(stream, group, message_id)

    async def reclaim_stale(
        self, stream: str, group: str, consumer: str, *, min_idle_ms: int, count: int = 10
    ) -> list[Message]:
        # XAUTOCLAIM (stream, group, consumer, min-idle-time, start)
        _cursor, entries, _deleted = await self._redis.xautoclaim(
            stream, group, consumer, min_idle_ms, start_id="0-0", count=count
        )
        return [self._to_message(stream, mid, fields) for mid, fields in entries]

    async def to_dead_letter(self, message: Message, *, error: str) -> None:
        await self._redis.xadd(
            self._dlq_stream,
            {
                b"origin": message.stream.encode(),
                b"data": orjson.dumps(message.payload),
                b"attempts": str(message.attempts).encode(),
                b"error": error.encode()[:2000],
            },
        )
        # Caller is responsible for ACKing the poison message off the main stream.
        log.error(
            "message_dead_lettered",
            origin=message.stream,
            attempts=message.attempts,
            error=error,
        )

    async def lag(self, stream: str, group: str) -> int:
        try:
            info = await self._redis.xpending(stream, group)
        except Exception:  # noqa: BLE001 — group/stream may not exist yet
            return 0
        # xpending summary form returns {'pending': N, ...}
        if isinstance(info, dict):
            return int(info.get("pending", 0))
        return int(info[0]) if info else 0
