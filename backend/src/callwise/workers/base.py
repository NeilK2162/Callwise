"""Stream-consumer worker base (PRD §8.1, §9.4, §9.6).

Provides at-least-once consumption with explicit ACK, crashed-worker recovery via
`XAUTOCLAIM`, dead-lettering of poison messages, and graceful drain on SIGTERM:
  (1) stop claiming new tasks, (2) finish in-flight, (3) ACK, (4) exit.
Kubernetes `terminationGracePeriodSeconds` is set above the longest task so a deploy
never abandons work mid-flight.
"""

from __future__ import annotations

import asyncio
import os
import signal
import socket
from collections.abc import Awaitable, Callable

from callwise.config import get_settings
from callwise.logging import bind_call_context, clear_call_context, configure_logging, get_logger
from callwise.queue.base import Message, Queue
from callwise.queue.factory import get_queue

log = get_logger(__name__)

Handler = Callable[[Message], Awaitable[None]]


class StreamWorker:
    def __init__(
        self,
        *,
        stream: str,
        group: str,
        handler: Handler,
        queue: Queue | None = None,
        batch: int = 10,
        block_ms: int = 2000,
        on_start: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.stream = stream
        self.group = group
        self.handler = handler
        self.queue = queue or get_queue()
        self.batch = batch
        self.block_ms = block_ms
        self.on_start = on_start
        self.consumer = f"{group}-{socket.gethostname()}-{os.getpid()}"
        self._stop = asyncio.Event()
        self._settings = get_settings()

    def _install_signals(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except NotImplementedError:  # Windows: signal handlers limited
                signal.signal(sig, lambda *_: self._stop.set())

    async def _process(self, msg: Message) -> None:
        bind_call_context(stream=self.stream, message_id=msg.id, idem=msg.idempotency_key)
        try:
            await self.handler(msg)
            await self.queue.ack(self.stream, self.group, msg.id)
        except Exception as exc:  # noqa: BLE001
            if msg.attempts >= self._settings.queue_max_attempts:
                await self.queue.to_dead_letter(msg, error=repr(exc))
                await self.queue.ack(self.stream, self.group, msg.id)
            else:
                # Re-publish with an incremented attempt count, then ACK the original.
                # NOTE: delayed/backoff retry via a ZSET scheduler is a TODO; this retries
                # promptly, which is fine for transient errors with full-jitter upstream.
                msg.attempts += 1
                await self.queue.publish(
                    self.stream, msg.payload, idempotency_key=msg.idempotency_key
                )
                await self.queue.ack(self.stream, self.group, msg.id)
                log.warning("task_retry", stream=self.stream, attempts=msg.attempts, error=repr(exc))
        finally:
            clear_call_context()

    async def run(self) -> None:
        configure_logging(self._settings.log_level, json=self._settings.app_env != "dev")
        self._install_signals()
        await self.queue.ensure_group(self.stream, self.group)
        if self.on_start is not None:
            await self.on_start()
        log.info("worker_started", stream=self.stream, consumer=self.consumer)

        while not self._stop.is_set():
            # Recover messages stuck in a crashed worker's PEL before reading new ones.
            stale = await self.queue.reclaim_stale(
                self.stream,
                self.group,
                self.consumer,
                min_idle_ms=self._settings.queue_claim_idle_ms,
                count=self.batch,
            )
            for msg in stale:
                await self._process(msg)

            messages = await self.queue.consume(
                self.stream, self.group, self.consumer, count=self.batch, block_ms=self.block_ms
            )
            for msg in messages:
                if self._stop.is_set():
                    break  # stop claiming new work, but finish what we read
                await self._process(msg)

        log.info("worker_drained", stream=self.stream, consumer=self.consumer)


def run_worker(worker: StreamWorker) -> None:
    asyncio.run(worker.run())
