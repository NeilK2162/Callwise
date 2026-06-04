"""Broker abstraction (PRD §8.1).

Default implementation is Redis Streams + consumer groups (`RedisStreamsQueue`). The
interface is deliberately narrow so the broker can be swapped for SQS at true scale by
writing one adapter — the documented migration path. Everything downstream depends only
on `Queue`, never on Redis directly.

Delivery is **at-least-once** with explicit ACK; idempotent task bodies (claim, CAS,
upserts) make a double-delivery a no-op (PRD §6.5).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Message:
    id: str
    stream: str
    payload: dict[str, Any]
    idempotency_key: str | None = None
    attempts: int = 1
    meta: dict[str, Any] = field(default_factory=dict)


class Queue(ABC):
    @abstractmethod
    async def ensure_group(self, stream: str, group: str) -> None:
        """Create the consumer group (idempotent; MKSTREAM)."""

    @abstractmethod
    async def publish(
        self, stream: str, payload: dict[str, Any], *, idempotency_key: str | None = None
    ) -> str:
        """Append a message; return its id."""

    @abstractmethod
    async def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        count: int = 10,
        block_ms: int = 2000,
    ) -> list[Message]:
        """Read new messages for this consumer (blocking up to block_ms)."""

    @abstractmethod
    async def ack(self, stream: str, group: str, message_id: str) -> None:
        """Acknowledge a processed message (removes it from the PEL)."""

    @abstractmethod
    async def reclaim_stale(
        self, stream: str, group: str, consumer: str, *, min_idle_ms: int, count: int = 10
    ) -> list[Message]:
        """Claim messages stuck in another (crashed) consumer's PEL — XAUTOCLAIM."""

    @abstractmethod
    async def to_dead_letter(self, message: Message, *, error: str) -> None:
        """Move a poison message to the DLQ after max attempts (PRD §9.4)."""

    @abstractmethod
    async def lag(self, stream: str, group: str) -> int:
        """Pending-entries count — the KEDA autoscaling signal (PRD §15.2)."""
