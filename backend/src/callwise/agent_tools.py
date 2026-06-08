"""Orchestrator-neutral conversation tools (PRD §0.4, §12).

The four things the receptionist can *do* on a live call — check availability, book on
Cal.com, take a message, honor do-not-contact — as provider-agnostic async functions that
return a normalized result instead of raising. Both orchestrators call these, so the booking
logic + edge-case handling live in ONE place and the conversation engine is swappable:

  * LiveKit (own the audio loop): `@function_tool` methods translate a ToolResult into the
    SDK's exception-based control flow (re-offer on `unavailable`, message on `error`).
  * ElevenLabs Agent (they own the loop): the server-tool webhooks in
    `webhook_ingest/routers/agent_tools.py` return the ToolResult's `say` to the agent.

Mid-call outcomes are stashed in Redis keyed by the orchestrator's call id (the ElevenLabs
`conversation_id`) so the post-call verifier can apply the *authoritative* outcome — the real
Cal.com booking uid, the message, the opt-out — to the query card, exactly like the LiveKit
agent posts `booking`/`message`/`opted_out` in its shutdown payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import orjson

from callwise.booking import BookingError, BookingUnavailable, get_booking_provider
from callwise.config import get_settings
from callwise.logging import get_logger
from callwise.redis_pool import get_redis

log = get_logger(__name__)

_STASH_PREFIX = "agent:outcome:"


@dataclass(slots=True)
class ToolResult:
    """The normalized result of a conversation tool.

    `say` is natural language the agent speaks/acts on; `status` drives orchestrator control
    flow; `outcome` is the authoritative record to persist onto the card (booking/message/
    opted_out/caller_id); `data` carries structured extras (e.g. the slot list).
    """

    say: str
    status: str  # ok | unavailable | no_slots | error
    outcome: dict | None = None
    data: dict | None = None


def _friendly(iso: str) -> str:
    """ISO-8601 UTC → 'Friday Jun 13 at 03:00 PM' in the clinic's timezone."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(
            ZoneInfo(get_settings().calcom_timezone)
        )
        return dt.strftime("%A %b %d at %I:%M %p")
    except (ValueError, OverflowError):
        return iso


def _parse_instant(iso: str) -> datetime:
    """Parse an ISO-8601 time to an aware datetime; naive input assumes the clinic timezone."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(get_settings().calcom_timezone))
    return dt


def _same_minute(a: datetime, b: datetime) -> bool:
    """Two instants are the same appointment time if they match to the minute (UTC)."""
    return a.astimezone(UTC).replace(second=0, microsecond=0) == b.astimezone(UTC).replace(
        second=0, microsecond=0
    )


# ── The four behaviors ──────────────────────────────────────────────────────
async def check_availability(preference: str | None = None, *, limit: int = 6) -> ToolResult:
    """Read the next open appointment slots. Graceful when Cal.com is down/unconfigured."""
    try:
        slots = await get_booking_provider().available_slots(limit=limit)
    except BookingError:
        return ToolResult(
            say="I can't reach the calendar right now — I can take a message and the desk "
            "will call you back to lock in a time.",
            status="error",
        )
    if not slots:
        return ToolResult(
            say="There's nothing open in the next week. Offer to take a message so the front "
            "desk can find a time that works.",
            status="no_slots",
        )
    options = [{"when": _friendly(s.start_iso), "slot_iso": s.start_iso} for s in slots]
    spoken = "; ".join(o["when"] for o in options[:3])
    return ToolResult(
        say=f"Open times: {spoken}. Offer two or three in plain language; when the caller "
        "picks one, pass its slot_iso to book_appointment.",
        status="ok",
        data={"slots": options},
    )


async def check_time(desired_iso: str) -> ToolResult:
    """Verify ONE specific time the caller named ("Thursday at 3?"). Confirms it's open, or —
    when it isn't — offers the nearest alternatives that day. Use this for a named time;
    use check_availability when the caller is flexible."""
    try:
        target = _parse_instant(desired_iso)
    except (ValueError, OverflowError):
        return ToolResult(
            say="I didn't quite catch an exact time — what day and time were you thinking?",
            status="error",
        )
    tz = ZoneInfo(get_settings().calcom_timezone)
    provider = get_booking_provider()
    try:
        day_slots = await provider.available_slots(on_date=target.astimezone(tz).date(), limit=48)
    except BookingError:
        return ToolResult(
            say="I can't reach the calendar right now — I can take a message and the desk will "
            "call you back to lock it in.",
            status="error",
        )
    for s in day_slots:
        try:
            if _same_minute(_parse_instant(s.start_iso), target):
                return ToolResult(
                    say=f"Yes — {_friendly(s.start_iso)} is open. Want me to book it?",
                    status="ok",
                    data={
                        "slot_iso": s.start_iso,
                        "slots": [{"when": _friendly(s.start_iso), "slot_iso": s.start_iso}],
                    },
                )
        except (ValueError, OverflowError):
            continue
    if day_slots:
        alternatives = day_slots
    else:
        try:
            alternatives = await provider.available_slots(limit=6)
        except BookingError:
            alternatives = []
    spoken = "; ".join(_friendly(s.start_iso) for s in alternatives[:3]) or "nothing else that day"
    return ToolResult(
        say=f"That exact time isn't open. The closest I have is {spoken}. Would any of those work?",
        status="unavailable",
        data={"slots": [{"when": _friendly(s.start_iso), "slot_iso": s.start_iso} for s in alternatives]},
    )


async def book_appointment(
    name: str, email: str, slot_iso: str, *, phone: str | None = None
) -> ToolResult:
    """Create a confirmed booking. Splits the two failure modes the agent must handle
    differently: `unavailable` (re-offer another time) vs `error` (take a message)."""
    provider = get_booking_provider()
    try:
        booking = await provider.create_booking(
            start_iso=slot_iso, name=name, email=email, phone=phone
        )
    except BookingUnavailable:
        try:
            slots = await provider.available_slots(limit=6)
        except BookingError:
            slots = []
        spoken = "; ".join(_friendly(s.start_iso) for s in slots) or "no other times this week"
        return ToolResult(
            say=f"That time was just taken. Offer another: {spoken}.",
            status="unavailable",
            data={"slots": [{"when": _friendly(s.start_iso), "slot_iso": s.start_iso} for s in slots]},
        )
    except BookingError:
        return ToolResult(
            say="I'm having trouble confirming that this second — tell the caller you've taken "
            "their details and the desk will confirm shortly.",
            status="error",
            outcome={
                "message": {
                    "name": name,
                    "email": email,
                    "reason": "booking_failed",
                    "slot": slot_iso,
                    "phone": phone,
                }
            },
        )
    return ToolResult(
        say=f"Booked {name} for {_friendly(booking.start_iso)}. A confirmation has been sent.",
        status="ok",
        outcome={"booking": {"uid": booking.uid, "start": booking.start_iso, "name": name, "email": email}},
    )


async def take_message(
    name: str,
    reason: str,
    *,
    details: str | None = None,
    callback_window: str | None = None,
    phone: str | None = None,
) -> ToolResult:
    """Capture a callback when the agent can't finish live — no time, no email, reschedule/
    cancel, wants a human, or an unanswered question. Maps to `callback_needed` on the card."""
    return ToolResult(
        say="Got it — I've noted that and the front desk will follow up. Anything else?",
        status="ok",
        outcome={
            "message": {
                "name": name,
                "reason": reason,
                "details": details,
                "callback_window": callback_window,
                "phone": phone,
            }
        },
    )


def mark_do_not_contact() -> ToolResult:
    """Honor a stop-contact request. Maps to `opt_out` (suppressed across all campaigns)."""
    return ToolResult(
        say="Done — I've removed you from our calling list. Sorry for the trouble.",
        status="ok",
        outcome={"opted_out": True},
    )


# ── Mid-call outcome stash (keyed by the orchestrator's call id) ─────────────
async def stash_outcome(call_id: str | None, outcome: dict | None) -> None:
    """Merge an outcome (booking/message/opted_out/caller_id) into the call's Redis hash so
    the post-call verifier can apply it authoritatively. Fields overwrite (a later booking
    supersedes an earlier message); the verifier applies opt-out > booking > message."""
    if not call_id or not outcome:
        return
    mapping = {k: orjson.dumps(v).decode() for k, v in outcome.items() if v is not None}
    if not mapping:
        return
    redis = get_redis()
    key = _STASH_PREFIX + str(call_id)
    await redis.hset(key, mapping=mapping)
    await redis.expire(key, get_settings().agent_tools_outcome_ttl_seconds)


async def load_outcome(call_id: str | None) -> dict:
    """Read back the stashed outcome for a call id. Returns {} when nothing was recorded."""
    if not call_id:
        return {}
    raw = await get_redis().hgetall(_STASH_PREFIX + str(call_id))
    out: dict = {}
    for k, v in (raw or {}).items():
        key = k.decode() if isinstance(k, bytes | bytearray) else k
        val = v.decode() if isinstance(v, bytes | bytearray) else v
        try:
            out[key] = orjson.loads(val)
        except orjson.JSONDecodeError:
            out[key] = val
    return out
