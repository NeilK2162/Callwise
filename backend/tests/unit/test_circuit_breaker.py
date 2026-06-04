"""Circuit breaker — fail-fast while open, half-open probe, recovery (PRD §9.2)."""

from __future__ import annotations

import asyncio
import time

import pytest

from callwise.governors.circuit_breaker import CircuitBreaker, CircuitOpen


async def _ok() -> str:
    return "ok"


async def _boom() -> None:
    raise RuntimeError("provider down")


async def test_closed_passes_through():
    cb = CircuitBreaker("exotel", fail_threshold=2, window_s=60, cool_down_s=1)
    assert await cb.call(_ok) == "ok"
    assert cb.state == "closed"


async def test_failures_open_circuit_and_reject_fast():
    cb = CircuitBreaker("exotel", fail_threshold=2, window_s=60, cool_down_s=60)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(_boom)
    assert cb.state == "open"
    with pytest.raises(CircuitOpen):
        await cb.call(_ok)


async def test_half_open_success_closes_circuit():
    cb = CircuitBreaker("exotel", fail_threshold=1, window_s=60, cool_down_s=0.05)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    assert cb.state == "open"
    await asyncio.sleep(0.06)
    assert await cb.call(_ok) == "ok"
    assert cb.state == "closed"


async def test_failures_outside_window_do_not_accumulate():
    cb = CircuitBreaker("exotel", fail_threshold=2, window_s=0.05, cool_down_s=60)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    time.sleep(0.06)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    # One failure pruned — still closed.
    assert cb.state == "closed"
