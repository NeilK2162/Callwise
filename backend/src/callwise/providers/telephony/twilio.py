"""Twilio adapter — STUB.

Twilio supports a native `Idempotency-Key` header, so a retried `place_call` with the same
`call_session_id` won't create a second call. Default per-number rate is ~1 call/sec; use
a number pool + rate spreading for higher throughput (PRD §4.2). Requires the optional
`telephony` extra (`uv sync --extra telephony`).
"""

from __future__ import annotations

from callwise.config import Settings
from callwise.db.enums import CallStatus
from callwise.providers.telephony.base import PlaceCallResult, TelephonyProvider


class TwilioProvider(TelephonyProvider):
    name = "twilio"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # from twilio.rest import Client
        # self._client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

    async def place_call(
        self,
        *,
        to: str,
        idempotency_key: str,
        context_url: str,
        from_number: str | None = None,
        max_duration_s: int = 300,
    ) -> PlaceCallResult:
        # TODO: client.calls.create(to=to, from_=..., url=context_url,
        #       status_callback=..., time_limit=max_duration_s)
        #       passing Idempotency-Key=idempotency_key on the request.
        raise NotImplementedError("Twilio adapter not yet implemented")

    async def get_call_status(self, provider_call_id: str) -> CallStatus:
        raise NotImplementedError("Twilio adapter not yet implemented")

    async def hangup(self, provider_call_id: str) -> None:
        raise NotImplementedError("Twilio adapter not yet implemented")
