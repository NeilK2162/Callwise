"""Per-provider circuit breaker (PRD §9.2).

Stops hammering a failing provider, fails fast while it's down, and auto-probes recovery.
When the breaker is open, dialing for that provider pauses (contacts stay `queued`) and a
background probe transitions to half-open after the cooldown.

This is an in-process breaker (per worker); for a cluster-wide view, the failure counts
can be mirrored to Redis. Per-worker breaking is usually sufficient because all workers
hit the same failing provider and open near-simultaneously.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class CircuitOpen(Exception):
    def __init__(self, name: str = "provider") -> None:
        super().__init__(f"circuit open for {name}")
        self.name = name


class CircuitBreaker:
    """States: closed (normal) → open (reject fast) → half_open (probe)."""

    def __init__(
        self,
        name: str = "provider",
        *,
        fail_threshold: int = 20,
        window_s: float = 30,
        cool_down_s: float = 15,
    ) -> None:
        self.name = name
        self.fail_threshold = fail_threshold
        self.window_s = window_s
        self.cool_down_s = cool_down_s
        self.state = "closed"
        self._failures: deque[float] = deque()
        self._opened_at: float | None = None

    def _prune(self, now: float) -> None:
        while self._failures and now - self._failures[0] > self.window_s:
            self._failures.popleft()

    async def call(self, fn: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        now = time.monotonic()
        if self.state == "open":
            if self._opened_at is not None and now - self._opened_at >= self.cool_down_s:
                self.state = "half_open"
            else:
                raise CircuitOpen(self.name)
        try:
            result = await fn(*args, **kwargs)
        except Exception:
            self._failures.append(now)
            self._prune(now)
            if len(self._failures) >= self.fail_threshold:
                self.state = "open"
                self._opened_at = now
            raise
        else:
            if self.state == "half_open":
                self.state = "closed"
                self._failures.clear()
            return result
