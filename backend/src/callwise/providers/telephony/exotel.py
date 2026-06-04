"""Exotel adapter (India PSTN) — STUB.

Exotel licenses concurrent channels and caps API QPS, so the concurrency governor and the
per-provider token bucket are both keyed on "exotel" upstream of this adapter (PRD §4.2).
Exotel has no native idempotency header, so we correlate via `CustomField` carrying our
`call_session_id`; combined with the write-ahead session row + reconciler, a retried
dispatch is caught before a second call is placed (PRD §6.2).
"""

from __future__ import annotations

import httpx

from callwise.config import Settings
from callwise.db.enums import CallStatus
from callwise.providers.telephony.base import PlaceCallResult, TelephonyProvider


class ExotelProvider(TelephonyProvider):
    name = "exotel"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=10.0)
        # base = f"https://{sid}:{token}@{subdomain}/v1/Accounts/{sid}"

    async def place_call(
        self,
        *,
        to: str,
        idempotency_key: str,
        context_url: str,
        from_number: str | None = None,
        max_duration_s: int = 300,
    ) -> PlaceCallResult:
        # TODO: POST /Calls/connect.json with CustomField=idempotency_key,
        #       StatusCallback -> /api/v2/webhooks/exotel/call-status,
        #       Url -> context_url (short-lived signed token, PRD §14.4).
        raise NotImplementedError("Exotel adapter not yet implemented")

    async def get_call_status(self, provider_call_id: str) -> CallStatus:
        # TODO: GET /Calls/{provider_call_id}.json and map Status -> CallStatus.
        raise NotImplementedError("Exotel adapter not yet implemented")

    async def hangup(self, provider_call_id: str) -> None:
        raise NotImplementedError("Exotel adapter not yet implemented")
