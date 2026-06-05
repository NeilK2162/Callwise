"""Plivo adapter. Ref: plivo.com/docs/voice/api/call.

POST /v1/Account/{auth_id}/Call/ (basic auth). `answer_url` points at our agent bridge;
`hangup_url` is our status webhook; `machine_detection` enables AMD. Plivo is
webhook-driven — the real CallUUID arrives on the callback (we map it to
`provider_call_id` there); `get_call_status` polling is best-effort.
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

_STATUS_MAP: dict[str, CallStatus] = {
    "queued": CallStatus.dialing,
    "ringing": CallStatus.ringing,
    "in-progress": CallStatus.in_progress,
    "answer": CallStatus.in_progress,
    "completed": CallStatus.completed,
    "busy": CallStatus.busy,
    "failed": CallStatus.failed,
    "no-answer": CallStatus.no_answer,
    "timeout": CallStatus.no_answer,
    "cancel": CallStatus.canceled,
}


def map_plivo_status(value: str | None) -> CallStatus:
    return _STATUS_MAP.get((value or "").strip().lower(), CallStatus.failed)


class PlivoProvider(TelephonyProvider):
    name = "plivo"

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        if not (settings.plivo_auth_id and settings.plivo_auth_token):
            raise ProviderError("Plivo credentials not configured", reason="config")
        self._base = f"https://api.plivo.com/v1/Account/{settings.plivo_auth_id}"
        self._auth = (settings.plivo_auth_id, settings.plivo_auth_token)

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
            "from": from_number or self._s.plivo_from,
            "to": to,
            "answer_url": context_url,
            "answer_method": "GET",
            "hangup_url": f"{self._s.base_url}/api/v2/webhooks/plivo",
            "time_limit": max_duration_s,
            "machine_detection": "true",
        }
        async with httpx.AsyncClient(timeout=15.0, auth=self._auth) as client:
            resp = await client.post(f"{self._base}/Call/", json=body)
        if resp.status_code == 429:
            raise ProviderRateLimitedError("plivo 429", retry_after_ms=1000)
        if resp.status_code >= 500:
            raise ProviderError(f"plivo {resp.status_code}", reason="provider_5xx")
        if resp.status_code >= 400:
            raise TerminalProviderError(f"plivo {resp.status_code}: {resp.text[:200]}")
        data = resp.json() or {}
        request_uuid = (data.get("request_uuid") or [None])
        rid = request_uuid[0] if isinstance(request_uuid, list) else request_uuid
        return PlaceCallResult(provider_call_id=str(rid), accepted=True)

    async def get_call_status(self, provider_call_id: str) -> CallStatus:
        async with httpx.AsyncClient(timeout=10.0, auth=self._auth) as client:
            resp = await client.get(f"{self._base}/Call/{provider_call_id}/")
        if resp.status_code >= 400:
            return CallStatus.failed
        body = resp.json() or {}
        return map_plivo_status(body.get("call_status") or body.get("call_state"))

    async def hangup(self, provider_call_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0, auth=self._auth) as client:
            await client.delete(f"{self._base}/Call/{provider_call_id}/")
