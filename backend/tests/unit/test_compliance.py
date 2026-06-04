from datetime import UTC, datetime

from callwise.compliance import is_callable_now, within_calling_window
from callwise.db.enums import ContactStatus
from callwise.db.models import Campaign, Contact


def _contact(tz: str = "Asia/Kolkata", status: ContactStatus = ContactStatus.queued) -> Contact:
    return Contact(timezone=tz, status=status, phone_e164="+919876543210")


def _campaign(provider: str = "exotel", dial_window: dict | None = None) -> Campaign:
    return Campaign(name="c", provider=provider, dial_window=dial_window or {})


# 06:30 UTC == 12:00 IST (inside default 09:00–21:00); 21:30 UTC == 03:00 IST next day (outside).
_NOON_IST = datetime(2026, 6, 5, 6, 30, tzinfo=UTC)
_3AM_IST = datetime(2026, 6, 5, 21, 30, tzinfo=UTC)


def test_within_window_midday():
    assert within_calling_window(_contact(), _campaign(), now=_NOON_IST) is True


def test_outside_window_at_night():
    assert within_calling_window(_contact(), _campaign(), now=_3AM_IST) is False


def test_custom_window_override():
    c = _campaign(dial_window={"start_hour": 0, "end_hour": 24})
    assert within_calling_window(_contact(), c, now=_3AM_IST) is True


def test_mock_provider_skips_window():
    # Simulated provider is callable at any hour so local demos work.
    assert is_callable_now(_contact(), _campaign(provider="mock"), now=_3AM_IST) is True


def test_real_provider_enforces_window():
    assert is_callable_now(_contact(), _campaign(provider="exotel"), now=_3AM_IST) is False


def test_do_not_contact_never_callable():
    c = _contact(status=ContactStatus.do_not_contact)
    assert is_callable_now(c, _campaign(provider="mock"), now=_NOON_IST) is False
