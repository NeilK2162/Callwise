"""Exotel adapter (India PSTN).

Implements the documented **Connect Two Numbers** API:
    POST https://<api_key>:<api_token>@<subdomain>/v1/Accounts/<sid>/Calls/connect.json
        From  — number/SIP dialed first (the agent leg; bridges to ElevenLabs ConvAI)
        To    — the customer (E.164)
        CallerId — your ExoPhone (virtual number)
        CustomField — our call_session_id (echoed back in StatusCallback → correlation)
        StatusCallback / StatusCallbackEvents / StatusCallbackContentType
        TimeLimit — hard max call duration

Exotel has no idempotency header, so we correlate via CustomField + the write-ahead
session row + reconciler (PRD §6.2). Status values per the StatusCallback docs:
queued / in-progress / completed / failed / busy / no-answer (legs add canceled).
Refs: developer.exotel.com/api/make-a-call-api, .../api-reference/status-callback
"""

from __future__ import annotations

import httpx

from callwise.config import Settings
from callwise.db.enums import CallStatus
from callwise.providers.errors import (
    ProviderError,
    ProviderRateLimitedError,
    TerminalProviderError,
)
from callwise.providers.telephony.base import PlaceCallResult, TelephonyProvider

# Exotel status string → our CallStatus.
_STATUS_MAP: dict[str, CallStatus] = {
    "queued": CallStatus.dialing,
    "in-progress": CallStatus.in_progress,
    "completed": CallStatus.completed,
    "failed": CallStatus.failed,
    "busy": CallStatus.busy,
    "no-answer": CallStatus.no_answer,
    "canceled": CallStatus.canceled,
}


def map_exotel_status(value: str | None) -> CallStatus:
    return _STATUS_MAP.get((value or "").strip().lower(), CallStatus.failed)


class ExotelProvider(TelephonyProvider):
    name = "exotel"

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        if not (settings.exotel_sid and settings.exotel_api_key and settings.exotel_api_token):
            raise ProviderError("Exotel credentials not configured", reason="config")
        self._base = f"https://{settings.exotel_subdomain}/v1/Accounts/{settings.exotel_sid}"
        self._auth = (settings.exotel_api_key, settings.exotel_api_token)

    async def place_call(
        self,
        *,
        to: str,
        idempotency_key: str,
        context_url: str,
        from_number: str | None = None,
        max_duration_s: int = 300,
    ) -> PlaceCallResult:
        # `From` is dialed first — the agent leg. For ElevenLabs ConvAI this is the SIP/number
        # that bridges to the agent; ElevenLabs fetches per-call context from context_url
        # keyed on our call_session_id (PRD §14.4).
        from_leg = from_number or self._s.exotel_from or self._s.exotel_caller_id
        form = {
            "From": from_leg,
            "To": to,
            "CallerId": self._s.exotel_caller_id,
            "CustomField": idempotency_key,
            "TimeLimit": str(max_duration_s),
            "StatusCallback": f"{self._s.base_url}/api/v2/webhooks/exotel/call-status",
            "StatusCallbackEvents": "terminal,answered",
            "StatusCallbackContentType": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0, auth=self._auth) as client:
            resp = await client.post(f"{self._base}/Calls/connect.json", data=form)

        if resp.status_code == 429:
            raise ProviderRateLimitedError("exotel 429", retry_after_ms=1000)
        if resp.status_code >= 500:
            raise ProviderError(f"exotel {resp.status_code}", reason="provider_5xx")
        if resp.status_code >= 400:
            # 4xx (e.g. invalid number) is terminal — don't retry into a credit-burning loop.
            raise TerminalProviderError(f"exotel {resp.status_code}: {resp.text[:200]}")

        call = (resp.json() or {}).get("Call", {})
        sid = call.get("Sid")
        if not sid:
            raise ProviderError("exotel response missing Call.Sid", reason="bad_response")
        return PlaceCallResult(provider_call_id=str(sid), accepted=True)

    async def get_call_status(self, provider_call_id: str) -> CallStatus:
        async with httpx.AsyncClient(timeout=10.0, auth=self._auth) as client:
            resp = await client.get(f"{self._base}/Calls/{provider_call_id}.json")
        if resp.status_code >= 400:
            return CallStatus.failed
        call = (resp.json() or {}).get("Call", {})
        return map_exotel_status(call.get("Status"))

    async def hangup(self, provider_call_id: str) -> None:
        # Exotel enforces the hard ceiling via TimeLimit on connect; there is no generic
        # hangup-by-Sid on the connect flow. Force-end is therefore provider-side.
        return None
