"""Twilio adapter.

Implements the documented Programmable Voice CreateCall:
    POST /2010-04-01/Accounts/{AccountSid}/Calls.json
        To, From, Url (TwiML/agent), StatusCallback, StatusCallbackEvent[],
        MachineDetection (AMD → voicemail detection), TimeLimit (hard ceiling)
Carries our call_session_id as the `Idempotency-Key` header so a retried create won't
place a second call (PRD §6.2). Implemented over httpx so the core needs no Twilio SDK;
install the optional `telephony` extra only if you prefer the SDK.

Status values: queued / ringing / in-progress / completed / busy / failed / no-answer /
canceled. Ref: twilio.com/docs (api_v2010 CreateCall).
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
    "completed": CallStatus.completed,
    "busy": CallStatus.busy,
    "failed": CallStatus.failed,
    "no-answer": CallStatus.no_answer,
    "canceled": CallStatus.canceled,
}


def map_twilio_status(value: str | None) -> CallStatus:
    return _STATUS_MAP.get((value or "").strip().lower(), CallStatus.failed)


class TwilioProvider(TelephonyProvider):
    name = "twilio"

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        if not (settings.twilio_account_sid and settings.twilio_auth_token):
            raise ProviderError("Twilio credentials not configured", reason="config")
        self._base = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}"
        self._auth = (settings.twilio_account_sid, settings.twilio_auth_token)

    async def place_call(
        self,
        *,
        to: str,
        idempotency_key: str,
        context_url: str,
        from_number: str | None = None,
        max_duration_s: int = 300,
    ) -> PlaceCallResult:
        data = {
            "To": to,
            "From": from_number or self._s.twilio_from_number,
            "Url": context_url,  # TwiML / agent bridge URL
            "StatusCallback": f"{self._s.base_url}/api/v2/webhooks/twilio",
            "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
            "StatusCallbackMethod": "POST",
            "MachineDetection": "DetectMessageEnd",  # AMD → AnsweredBy on the callback
            "TimeLimit": str(max_duration_s),
        }
        async with httpx.AsyncClient(timeout=15.0, auth=self._auth) as client:
            resp = await client.post(
                f"{self._base}/Calls.json",
                data=data,
                headers={"Idempotency-Key": idempotency_key},
            )

        if resp.status_code == 429:
            raise ProviderRateLimitedError("twilio 429", retry_after_ms=1000)
        if resp.status_code >= 500:
            raise ProviderError(f"twilio {resp.status_code}", reason="provider_5xx")
        if resp.status_code >= 400:
            raise TerminalProviderError(f"twilio {resp.status_code}: {resp.text[:200]}")

        body = resp.json() or {}
        sid = body.get("sid")
        if not sid:
            raise ProviderError("twilio response missing sid", reason="bad_response")
        return PlaceCallResult(provider_call_id=str(sid), accepted=True)

    async def get_call_status(self, provider_call_id: str) -> CallStatus:
        async with httpx.AsyncClient(timeout=10.0, auth=self._auth) as client:
            resp = await client.get(f"{self._base}/Calls/{provider_call_id}.json")
        if resp.status_code >= 400:
            return CallStatus.failed
        return map_twilio_status((resp.json() or {}).get("status"))

    async def hangup(self, provider_call_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0, auth=self._auth) as client:
            await client.post(
                f"{self._base}/Calls/{provider_call_id}.json", data={"Status": "completed"}
            )
