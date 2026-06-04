"""In-memory mock telephony provider — the "fake provider" of PRD §16.2.

It simulates the full PSTN lifecycle with realistic call durations and a configurable mix
of outcomes (answer / no-answer / busy / voicemail / rate-limit), then drives the post-call
flow exactly like a real provider would: after a short delay it POSTs a synthetic webhook
to the webhook-ingest service. That exercises the real ingest → dedup → verify pipeline
end-to-end with zero external dependencies, so the whole product is testable locally.
"""

from __future__ import annotations

import asyncio
import random

import httpx

from callwise.db.enums import CallStatus
from callwise.logging import get_logger
from callwise.providers.errors import ProviderRateLimitedError, TerminalProviderError
from callwise.providers.telephony.base import PlaceCallResult, TelephonyProvider

log = get_logger(__name__)

# Outcome mix roughly mirroring a real outbound campaign (tunable for load tests).
_OUTCOME_WEIGHTS: dict[CallStatus, float] = {
    CallStatus.completed: 0.62,
    CallStatus.no_answer: 0.18,
    CallStatus.voicemail: 0.10,
    CallStatus.busy: 0.06,
    CallStatus.failed: 0.04,
}

# When a call is answered, which conversation outcome it produced (drives the transcript).
_COMPLETED_SCENARIOS: dict[str, float] = {
    "appointment_booked": 0.5,
    "question_answered": 0.3,
    "callback_needed": 0.15,
    "not_interested": 0.05,
}

# Keep references to in-flight simulation tasks so they aren't GC'd mid-flight.
_SIM_TASKS: set[asyncio.Task] = set()


def _weighted(weights: dict) -> object:
    return random.choices(list(weights), weights=list(weights.values()))[0]


class MockTelephonyProvider(TelephonyProvider):
    name = "mock"

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8001",
        simulate: bool = True,
        rate_limit_prob: float = 0.0,
        invalid_prob: float = 0.0,
        min_delay_s: float = 1.5,
        max_delay_s: float = 4.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._simulate = simulate
        self._rate_limit_prob = rate_limit_prob
        self._invalid_prob = invalid_prob
        self._min_delay = min_delay_s
        self._max_delay = max_delay_s

    async def place_call(
        self,
        *,
        to: str,
        idempotency_key: str,
        context_url: str,
        from_number: str | None = None,
        max_duration_s: int = 300,
    ) -> PlaceCallResult:
        if random.random() < self._rate_limit_prob:
            raise ProviderRateLimitedError("mock rate limit", retry_after_ms=500)
        if random.random() < self._invalid_prob:
            raise TerminalProviderError("mock invalid number", reason="invalid_number")

        provider_call_id = f"mock-{idempotency_key}"
        if self._simulate:
            task = asyncio.create_task(
                self._simulate_call(call_session_id=idempotency_key, provider_call_id=provider_call_id)
            )
            _SIM_TASKS.add(task)
            task.add_done_callback(_SIM_TASKS.discard)
        return PlaceCallResult(provider_call_id=provider_call_id, accepted=True)

    async def _simulate_call(self, *, call_session_id: str, provider_call_id: str) -> None:
        """Wait a realistic call duration, then post a synthetic post-call webhook."""
        await asyncio.sleep(random.uniform(self._min_delay, self._max_delay))
        status: CallStatus = _weighted(_OUTCOME_WEIGHTS)  # type: ignore[assignment]
        payload: dict = {
            "call_session_id": call_session_id,
            "provider_call_id": provider_call_id,
            "status": status.value,
        }
        if status is CallStatus.completed:
            payload["scenario"] = _weighted(_COMPLETED_SCENARIOS)
            payload["duration_s"] = random.randint(40, 180)
            payload["recording_url"] = f"mock://recordings/{call_session_id}.mp3"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{self._base_url}/api/v2/webhooks/mock", json=payload)
        except Exception as exc:  # noqa: BLE001 — best-effort simulation, never crash the worker
            log.warning("mock_webhook_post_failed", error=repr(exc), sid=call_session_id)

    async def get_call_status(self, provider_call_id: str) -> CallStatus:
        return _weighted(_OUTCOME_WEIGHTS)  # type: ignore[return-value]

    async def hangup(self, provider_call_id: str) -> None:
        return None
