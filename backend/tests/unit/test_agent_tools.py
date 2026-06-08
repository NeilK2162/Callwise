"""Orchestrator-neutral conversation tools (callwise.agent_tools).

These run for BOTH the LiveKit agent and the ElevenLabs Agent, so the edge-case contract —
book vs re-offer vs take-a-message — is pinned here, network-free, by faking the booking
provider. The two failure modes the agent must treat differently (`unavailable` → offer
another time; `error` → take a message) are the heart of it.
"""

from __future__ import annotations

import pytest

from callwise import agent_tools
from callwise.booking import Booking, BookingError, BookingUnavailable, Slot


class _FakeProvider:
    def __init__(
        self,
        *,
        slots: list[Slot] | None = None,
        booking: Booking | None = None,
        slots_exc: Exception | None = None,
        book_exc: Exception | None = None,
    ) -> None:
        self._slots = slots or []
        self._booking = booking
        self._slots_exc = slots_exc
        self._book_exc = book_exc

    async def available_slots(
        self, *, days_ahead: int = 7, limit: int = 5, on_date=None
    ) -> list[Slot]:
        if self._slots_exc:
            raise self._slots_exc
        return self._slots[:limit]

    async def create_booking(self, *, start_iso, name, email, phone=None) -> Booking:
        if self._book_exc:
            raise self._book_exc
        assert self._booking is not None
        return self._booking


def _patch(monkeypatch, provider: _FakeProvider) -> None:
    monkeypatch.setattr(agent_tools, "get_booking_provider", lambda: provider)


_SLOTS = [Slot(start_iso="2026-06-13T09:30:00Z"), Slot(start_iso="2026-06-13T11:00:00Z")]


async def test_check_availability_offers_slots(monkeypatch):
    _patch(monkeypatch, _FakeProvider(slots=_SLOTS))
    res = await agent_tools.check_availability("Saturday morning")
    assert res.status == "ok"
    assert res.data and len(res.data["slots"]) == 2
    assert res.data["slots"][0]["slot_iso"] == "2026-06-13T09:30:00Z"


async def test_check_availability_no_slots(monkeypatch):
    _patch(monkeypatch, _FakeProvider(slots=[]))
    res = await agent_tools.check_availability()
    assert res.status == "no_slots"
    assert res.outcome is None


async def test_check_availability_calendar_down_is_graceful(monkeypatch):
    _patch(monkeypatch, _FakeProvider(slots_exc=BookingError("cal.com 500")))
    res = await agent_tools.check_availability()
    assert res.status == "error"  # never raises — the agent takes a message instead


async def test_check_time_exact_match_confirms(monkeypatch):
    _patch(monkeypatch, _FakeProvider(slots=_SLOTS))
    res = await agent_tools.check_time("2026-06-13T09:30:00Z")
    assert res.status == "ok"
    assert res.data["slot_iso"] == "2026-06-13T09:30:00Z"


async def test_check_time_naive_input_assumes_clinic_tz(monkeypatch):
    # 09:30 IST == 04:00Z; a naive "09:30" must match the 04:00Z slot, not the 09:30Z one.
    _patch(monkeypatch, _FakeProvider(slots=[Slot(start_iso="2026-06-13T04:00:00Z")]))
    res = await agent_tools.check_time("2026-06-13T09:30:00")  # no tz → Asia/Kolkata (+05:30)
    assert res.status == "ok"


async def test_check_time_not_open_offers_alternatives(monkeypatch):
    _patch(monkeypatch, _FakeProvider(slots=_SLOTS))
    res = await agent_tools.check_time("2026-06-13T16:45:00Z")  # not in the slot set
    assert res.status == "unavailable"
    assert res.data and len(res.data["slots"]) == 2


async def test_check_time_garbled_time_is_graceful(monkeypatch):
    _patch(monkeypatch, _FakeProvider(slots=_SLOTS))
    res = await agent_tools.check_time("sometime thursdayish")
    assert res.status == "error"  # re-asks instead of crashing


async def test_book_appointment_success(monkeypatch):
    booking = Booking(uid="bk_123", start_iso="2026-06-13T09:30:00Z", status="accepted")
    _patch(monkeypatch, _FakeProvider(booking=booking))
    res = await agent_tools.book_appointment("Asha Rao", "asha@example.com", "2026-06-13T09:30:00Z")
    assert res.status == "ok"
    assert res.outcome and res.outcome["booking"]["uid"] == "bk_123"
    assert res.outcome["booking"]["start"] == "2026-06-13T09:30:00Z"


async def test_book_appointment_slot_taken_reoffers(monkeypatch):
    # 409/422 → BookingUnavailable: re-offer fresh times, do NOT record an outcome.
    _patch(monkeypatch, _FakeProvider(slots=_SLOTS, book_exc=BookingUnavailable("taken")))
    res = await agent_tools.book_appointment("Asha", "a@b.com", "2026-06-13T09:30:00Z")
    assert res.status == "unavailable"
    assert res.outcome is None
    assert res.data and len(res.data["slots"]) == 2


async def test_book_appointment_system_error_takes_message(monkeypatch):
    # auth/5xx/network → BookingError: never strand the caller, fall back to a message.
    _patch(monkeypatch, _FakeProvider(book_exc=BookingError("cal.com 401")))
    res = await agent_tools.book_appointment("Asha", "a@b.com", "2026-06-13T09:30:00Z", phone="+91999")
    assert res.status == "error"
    assert res.outcome and res.outcome["message"]["reason"] == "booking_failed"
    assert res.outcome["message"]["phone"] == "+91999"


async def test_take_message_records_callback():
    res = await agent_tools.take_message(
        "Asha", "wants_human", details="prefers a person", callback_window="after 5pm"
    )
    assert res.status == "ok"
    assert res.outcome["message"]["reason"] == "wants_human"
    assert res.outcome["message"]["callback_window"] == "after 5pm"


def test_mark_do_not_contact():
    res = agent_tools.mark_do_not_contact()
    assert res.status == "ok"
    assert res.outcome == {"opted_out": True}


@pytest.mark.parametrize("iso", ["not-a-date", ""])
def test_friendly_is_resilient(iso):
    # A bad ISO string must never crash a tool — it degrades to the raw value.
    assert agent_tools._friendly(iso) == iso
