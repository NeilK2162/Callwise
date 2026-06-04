"""Telephony provider interface (PRD §1.1, §5.3).

PSTN providers are pluggable: Exotel, Twilio, Plivo, Telnyx. The dialer depends only on
this interface. `idempotency_key` (our `call_session_id`) is threaded end-to-end so a
retried dispatch that already reached the provider is detectable (PRD §6.2).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from callwise.db.enums import CallStatus


@dataclass(slots=True)
class PlaceCallResult:
    provider_call_id: str
    accepted: bool


class TelephonyProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def place_call(
        self,
        *,
        to: str,
        idempotency_key: str,
        context_url: str,
        from_number: str | None = None,
        max_duration_s: int = 300,
    ) -> PlaceCallResult:
        """Place an outbound call. MUST carry idempotency_key so a retry doesn't double-dial."""

    @abstractmethod
    async def get_call_status(self, provider_call_id: str) -> CallStatus:
        """Query true call state — used by the reconciler to resolve stale sessions (§5.6)."""

    @abstractmethod
    async def hangup(self, provider_call_id: str) -> None:
        """Force-end a call (e.g. max-duration breach)."""
