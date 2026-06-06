"""Appointment booking — live, confirmed bookings during the call (PRD §0.4).

The voice agent's `book_appointment` tool calls a `BookingProvider`. Cal.com is the default
because its v2 API supports **creating a confirmed booking** (unlike Calendly, whose public
API is invitee-driven and cannot finalize a booking server-side). The interface is provider-
neutral so Calendly-link / Google-Calendar variants can drop in.

Cal.com v2:
  * slots:    GET  /v2/slots    (cal-api-version: 2024-09-04)
  * booking:  POST /v2/bookings (cal-api-version: 2024-08-13)
Refs: cal.com/docs/api-reference/v2/bookings/create-a-booking
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from callwise.config import Settings, get_settings


@dataclass(slots=True)
class Slot:
    start_iso: str  # ISO 8601, UTC


@dataclass(slots=True)
class Booking:
    uid: str
    start_iso: str
    status: str


class BookingError(RuntimeError):
    """System/transport failure (auth, 5xx, network) — the agent should take a message."""


class BookingUnavailable(BookingError):
    """The requested slot is taken/invalid (4xx) — the agent should offer another time."""


class BookingProvider(ABC):
    @abstractmethod
    async def available_slots(self, *, days_ahead: int = 7, limit: int = 5) -> list[Slot]: ...

    @abstractmethod
    async def create_booking(
        self, *, start_iso: str, name: str, email: str, phone: str | None = None
    ) -> Booking: ...


class CalComProvider(BookingProvider):
    name = "calcom"

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        if not (settings.calcom_api_key and settings.calcom_event_type_id):
            raise BookingError("Cal.com not configured (CALCOM_API_KEY + CALCOM_EVENT_TYPE_ID)")
        self._base = "https://api.cal.com/v2"
        self._key = settings.calcom_api_key
        self._event_type_id = settings.calcom_event_type_id
        self._tz = settings.calcom_timezone

    async def available_slots(self, *, days_ahead: int = 7, limit: int = 5) -> list[Slot]:
        now = datetime.now(UTC)
        params = {
            "eventTypeId": self._event_type_id,
            "start": now.strftime("%Y-%m-%d"),
            "end": (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d"),
            "timeZone": self._tz,
        }
        headers = {
            "Authorization": f"Bearer {self._key}",
            "cal-api-version": self._s.calcom_api_version_slots,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self._base}/slots", params=params, headers=headers)
        if resp.status_code >= 400:
            raise BookingError(f"cal.com slots {resp.status_code}: {resp.text[:200]}")
        data = (resp.json() or {}).get("data", {})
        slots: list[Slot] = []
        # data is {"YYYY-MM-DD": [{"start": iso}, ...] | [iso, ...]}
        for items in (data.values() if isinstance(data, dict) else []):
            for item in items:
                iso = item.get("start") if isinstance(item, dict) else item
                if iso:
                    slots.append(Slot(start_iso=str(iso)))
                if len(slots) >= limit:
                    return slots
        return slots[:limit]

    async def create_booking(
        self, *, start_iso: str, name: str, email: str, phone: str | None = None
    ) -> Booking:
        attendee: dict = {"name": name, "email": email, "timeZone": self._tz, "language": "en"}
        if phone:
            attendee["phoneNumber"] = phone
        body = {"start": start_iso, "eventTypeId": self._event_type_id, "attendee": attendee}
        headers = {
            "Authorization": f"Bearer {self._key}",
            "cal-api-version": self._s.calcom_api_version_bookings,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{self._base}/bookings", json=body, headers=headers)
        if resp.status_code in (400, 409, 422):
            # Slot taken between read and book, or invalid time → offer an alternative.
            raise BookingUnavailable(f"slot unavailable: {resp.text[:160]}")
        if resp.status_code >= 400:
            raise BookingError(f"cal.com booking {resp.status_code}: {resp.text[:200]}")
        d = (resp.json() or {}).get("data", {})
        return Booking(
            uid=str(d.get("uid", "")),
            start_iso=str(d.get("start", start_iso)),
            status=str(d.get("status", "accepted")),
        )


def get_booking_provider(settings: Settings | None = None) -> BookingProvider:
    return CalComProvider(settings or get_settings())
