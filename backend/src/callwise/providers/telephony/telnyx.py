"""Telnyx Call Control adapter. Ref: developers.telnyx.com (Call Control v2).

POST /v2/calls (Bearer). Telnyx is fully webhook-driven (call.initiated / .answered /
.hangup with `hangup_cause`), so true state comes from those webhooks; `get_call_status`
polling isn't part of Call Control, so the reconciler falls back to `failed` (safe) if a
session goes stale without a terminal webhook.
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

# Telnyx hangup_cause → our status (used by the webhook router when implemented).
_HANGUP_CAUSE_MAP: dict[str, CallStatus] = {
    "normal_clearing": CallStatus.completed,
    "user_busy": CallStatus.busy,
    "no_answer": CallStatus.no_answer,
    "originator_cancel": CallStatus.canceled,
    "call_rejected": CallStatus.failed,
}


def map_telnyx_hangup_cause(value: str | None) -> CallStatus:
    return _HANGUP_CAUSE_MAP.get((value or "").strip().lower(), CallStatus.failed)


class TelnyxProvider(TelephonyProvider):
    name = "telnyx"

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        if not (settings.telnyx_api_key and settings.telnyx_connection_id):
            raise ProviderError("Telnyx credentials not configured", reason="config")
        self._base = "https://api.telnyx.com/v2"
        self._headers = {"Authorization": f"Bearer {settings.telnyx_api_key}"}

    async def place_call(
        self,
        *,
        to: str,
        idempotency_key: str,
        context_url: str,
        from_number: str | None = None,
        max_duration_s: int = 300,
    ) -> PlaceCallResult:
        body = {
            "connection_id": self._s.telnyx_connection_id,
            "to": to,
            "from": from_number or self._s.telnyx_from,
            "webhook_url": f"{self._s.base_url}/api/v2/webhooks/telnyx",
            "timeout_secs": max_duration_s,
            "answering_machine_detection": "detect",
            "client_state": idempotency_key,  # echoed back on webhooks for correlation
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{self._base}/calls", json=body, headers=self._headers)
        if resp.status_code == 429:
            raise ProviderRateLimitedError("telnyx 429", retry_after_ms=1000)
        if resp.status_code >= 500:
            raise ProviderError(f"telnyx {resp.status_code}", reason="provider_5xx")
        if resp.status_code >= 400:
            raise TerminalProviderError(f"telnyx {resp.status_code}: {resp.text[:200]}")
        data = (resp.json() or {}).get("data", {})
        call_control_id = data.get("call_control_id")
        if not call_control_id:
            raise ProviderError("telnyx response missing call_control_id", reason="bad_response")
        return PlaceCallResult(provider_call_id=str(call_control_id), accepted=True)

    async def get_call_status(self, provider_call_id: str) -> CallStatus:
        # Call Control has no GET-status-by-id; true state arrives via webhooks.
        return CallStatus.failed

    async def hangup(self, provider_call_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{self._base}/calls/{provider_call_id}/actions/hangup", headers=self._headers
            )
