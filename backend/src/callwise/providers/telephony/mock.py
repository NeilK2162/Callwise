"""In-memory mock telephony provider.

The default provider for local dev and the load/chaos harness (PRD §16.2): it simulates
realistic outcomes (answer / no-answer / busy / voicemail / rate-limit) without any
external dependency, so the whole pipeline can be exercised end-to-end and SLOs measured.
"""

from __future__ import annotations

import random
import uuid

from callwise.db.enums import CallStatus
from callwise.providers.errors import ProviderRateLimitedError, TerminalProviderError
from callwise.providers.telephony.base import PlaceCallResult, TelephonyProvider

# Outcome mix roughly mirroring a real outbound campaign (tunable for load tests).
_OUTCOME_WEIGHTS: dict[CallStatus, float] = {
    CallStatus.completed: 0.55,
    CallStatus.no_answer: 0.20,
    CallStatus.voicemail: 0.10,
    CallStatus.busy: 0.08,
    CallStatus.failed: 0.07,
}


class MockTelephonyProvider(TelephonyProvider):
    name = "mock"

    def __init__(self, *, rate_limit_prob: float = 0.0, invalid_prob: float = 0.0) -> None:
        self._rate_limit_prob = rate_limit_prob
        self._invalid_prob = invalid_prob

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
        # Deterministic mapping from the idempotency key keeps a retried dispatch stable.
        return PlaceCallResult(provider_call_id=f"mock-{idempotency_key}", accepted=True)

    async def get_call_status(self, provider_call_id: str) -> CallStatus:
        statuses = list(_OUTCOME_WEIGHTS)
        return random.choices(statuses, weights=list(_OUTCOME_WEIGHTS.values()))[0]

    async def hangup(self, provider_call_id: str) -> None:
        return None

    @staticmethod
    def simulate_outcome() -> CallStatus:
        statuses = list(_OUTCOME_WEIGHTS)
        return random.choices(statuses, weights=list(_OUTCOME_WEIGHTS.values()))[0]

    @staticmethod
    def new_provider_call_id() -> str:
        return f"mock-{uuid.uuid4()}"
