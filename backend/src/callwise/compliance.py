"""Telephony compliance gates (PRD §14.2, edge cases #41–#43).

Calling-window enforcement (per contact timezone) and do-not-contact suppression. These
run at enqueue time (orchestrator) and again as a pre-dial check in the dialer. The
cross-campaign suppression list is extended in `domain/suppression.py`; this module owns
the time-window logic and the per-contact opt-out check.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from callwise.db.enums import ContactStatus
from callwise.db.models import Campaign, Contact

# Default legal calling windows in the contact's LOCAL time (override per campaign via
# campaign.dial_window = {"start_hour": int, "end_hour": int}).
#   * TCPA (US):   08:00–21:00 local
#   * TRAI (India): 09:00–21:00 local
# We default to the stricter 09:00–21:00; tune per jurisdiction in campaign config.
DEFAULT_WINDOW_START_HOUR = 9
DEFAULT_WINDOW_END_HOUR = 21
_FALLBACK_TZ = "Asia/Kolkata"


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or _FALLBACK_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(_FALLBACK_TZ)


def within_calling_window(
    contact: Contact, campaign: Campaign, *, now: datetime | None = None
) -> bool:
    window = campaign.dial_window or {}
    start = int(window.get("start_hour", DEFAULT_WINDOW_START_HOUR))
    end = int(window.get("end_hour", DEFAULT_WINDOW_END_HOUR))
    tz = _zone(contact.timezone)
    local = (now.astimezone(tz) if now else datetime.now(tz))
    return start <= local.hour < end


def is_callable_now(
    contact: Contact, campaign: Campaign, *, now: datetime | None = None
) -> bool:
    """True iff this contact may be dialed right now (not opted-out, inside window).

    The simulated `mock` provider skips the legal calling window so local/dev demos work
    at any hour; real providers always enforce it."""
    if contact.status == ContactStatus.do_not_contact:
        return False
    if campaign.provider == "mock":
        return True
    return within_calling_window(contact, campaign, now=now)
