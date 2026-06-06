"""Deployable LiveKit voice agent — a real AI receptionist that books appointments and
handles every edge case gracefully.

Soniox STT → LLM (OpenAI/Anthropic) → ElevenLabs TTS, composed by LiveKit Agents, reached
via a SIP trunk on your Twilio number (PRD §5.4). It answers, converses naturally, books a
real Cal.com appointment live, and — crucially — degrades gracefully: no slot, caller won't
share email, wants a human, reschedule/cancel, "stop calling me", wrong person, silence —
each has a defined, kind resolution that lands as the right outcome on the dashboard.

Conversation policy + edge-case matrix: docs/agent-conversation.md.
Run:  uv run python -m callwise.providers.conversation.livekit_agent start
Env:  SONIOX_API_KEY, ELEVEN_API_KEY, OPENAI_API_KEY|ANTHROPIC_API_KEY, LIVEKIT_*,
      BASE_URL, CLINIC_NAME, ELEVENLABS_VOICE_ID, AGENT_LLM_*, CALCOM_API_KEY, CALCOM_EVENT_TYPE_ID.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, RunContext, function_tool, room_io
from livekit.agents.llm import ToolError
from livekit.plugins import elevenlabs, silero, soniox

from callwise.booking import BookingError, BookingUnavailable, get_booking_provider
from callwise.config import get_settings

settings = get_settings()
WEBHOOK_BASE = settings.base_url
AGENT_NAME = settings.livekit_agent_name
CLINIC = settings.clinic_name

# A production receptionist policy. Short turns, confirm before acting, and a defined,
# graceful path for every edge case (each maps to a dashboard outcome).
SYSTEM_PROMPT = f"""\
You are the virtual receptionist for {CLINIC}, a dental clinic, on a live phone call.

VOICE: warm, concise, human. One question at a time. Never read URLs, IDs, or code aloud.
OPEN: greet, say you're an automated assistant, and that the call may be recorded, then ask
how you can help.

BOOKING (the main job):
1. Ask the caller's preferred day/time.
2. Call check_availability and offer 2–3 real options in plain language.
3. When they pick one, collect their full name and email. EMAIL IS ERROR-PRONE OVER THE
   PHONE — repeat the email and the name back and get a clear "yes" before booking.
4. Call book_appointment with the chosen slot_iso. Then read back the confirmed day + time
   and say a confirmation was sent. Do not claim a booking unless the tool succeeds.

EDGE CASES — handle every one, never dead-end:
- No times work / nothing available: apologize, then call take_message (reason
  "no_suitable_time") with their name + a good callback window so the desk follows up.
- Caller won't or can't give an email: that's fine — call take_message (reason
  "book_no_email") with their name; the front desk will confirm to their phone.
- Reschedule or cancel an existing appointment: you can't change existing bookings — call
  take_message (reason "reschedule" or "cancel") with details.
- Wants a human / front desk: call take_message (reason "wants_human").
- A question you can't answer (specific pricing, insurance, clinical advice): give general
  info if you truly know it, otherwise call take_message (reason "question") with the question.
- "Stop calling me" / remove me / do not call: call mark_do_not_contact, confirm warmly, end.
- Wrong person / not the patient, or caller can't verify identity: do NOT share any personal
  or appointment details; offer to take a general message; end politely.
- Silence or you can't understand after one re-prompt: offer to call back and end.

PRIVACY: never disclose another person's appointment or personal details to an unverified
caller. Booking new appointments only needs the caller's own name + email.
Keep it natural — you are the calm, capable front desk that never misses a call.
"""


def _build_llm():
    if settings.agent_llm_provider == "anthropic":
        from livekit.plugins import anthropic

        return anthropic.LLM(model=settings.agent_llm_model)
    from livekit.plugins import openai

    return openai.LLM(model=settings.agent_llm_model)


def _friendly(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(
            ZoneInfo(settings.calcom_timezone)
        )
        return dt.strftime("%A %b %d at %I:%M %p")
    except (ValueError, OverflowError):
        return iso


class ReceptionistAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self.caller_number: str | None = None
        self.booking: dict | None = None       # set on a confirmed booking
        self.message: dict | None = None        # set when a callback/message is taken
        self.opted_out: bool = False            # set on do-not-contact

    @function_tool()
    async def check_availability(self, context: RunContext, preference: str | None = None) -> str:
        """Read out the next open appointment slots. Call when the caller wants to book or asks
        what's available.

        Args:
            preference: optional natural-language hint like "Saturday morning" or "next week"
                to help you choose which of the returned slots to offer first.
        """
        try:
            slots = await get_booking_provider().available_slots(limit=6)
        except BookingError as exc:
            raise ToolError("I can't reach the calendar this second — I can take a message.") from exc
        if not slots:
            return "NO_SLOTS: nothing open in the next week. Offer to take a message (no_suitable_time)."
        return "Open slots (offer 2–3 in plain language; keep each slot_iso to book): " + "; ".join(
            f"{_friendly(s.start_iso)} (slot_iso={s.start_iso})" for s in slots
        )

    @function_tool()
    async def book_appointment(
        self, context: RunContext, name: str, email: str, slot_iso: str
    ) -> str:
        """Book the appointment. Only after the caller confirmed a specific slot and you read
        their name + email back to them.

        Args:
            name: caller's full name.
            email: caller's email (already confirmed by read-back).
            slot_iso: the chosen slot's ISO-8601 UTC start, exactly as given by check_availability.
        """
        context.disallow_interruptions()  # mutating write — don't leave a half-booking
        provider = get_booking_provider()
        try:
            booking = await provider.create_booking(start_iso=slot_iso, name=name, email=email)
        except BookingUnavailable:
            # Taken between read and book → re-offer fresh times (no message yet).
            try:
                slots = await provider.available_slots(limit=6)
            except BookingError:
                slots = []
            options = "; ".join(f"{_friendly(s.start_iso)} (slot_iso={s.start_iso})" for s in slots)
            raise ToolError(
                f"That time was just taken. Offer another: {options or 'none left this week'}."
            ) from None
        except BookingError as exc:
            # System failure → fall back to a message so the caller is never stranded.
            self.message = {"name": name, "email": email, "reason": "booking_failed", "slot": slot_iso}
            raise ToolError(
                "I'm having trouble confirming that right now — tell the caller you've taken "
                "their details and the desk will confirm shortly."
            ) from exc
        self.booking = {"uid": booking.uid, "start": booking.start_iso, "name": name, "email": email}
        return f"Booked {name} for {_friendly(booking.start_iso)}. Confirmation sent."

    @function_tool()
    async def take_message(
        self,
        context: RunContext,
        name: str,
        reason: str,
        details: str | None = None,
        callback_window: str | None = None,
    ) -> str:
        """Capture a callback/message when you can't complete a booking live — no suitable time,
        no email, reschedule/cancel, wants a human, or an unanswered question.

        Args:
            name: the caller's name.
            reason: one of no_suitable_time | book_no_email | reschedule | cancel | wants_human | question.
            details: the specifics (the question asked, the time they wanted, etc.).
            callback_window: when they'd like to be reached, if given.
        """
        self.message = {
            "name": name,
            "reason": reason,
            "details": details,
            "callback_window": callback_window,
            "phone": self.caller_number,
        }
        return "Got it — I've noted that and the front desk will follow up. Anything else?"

    @function_tool()
    async def mark_do_not_contact(self, context: RunContext) -> str:
        """Honor a caller's request to stop being contacted / be removed from calling lists."""
        self.opted_out = True
        return "Done — I've removed you from our calling list. Sorry for the trouble."


server = AgentServer()


def _caller_number(ctx: agents.JobContext) -> str | None:
    for participant in ctx.room.remote_participants.values():
        attrs = getattr(participant, "attributes", {}) or {}
        number = attrs.get("sip.phoneNumber") or attrs.get("sip.from") or attrs.get("sip.fromUser")
        if number:
            return number
    return None


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: agents.JobContext) -> None:
    call_session_id = str(uuid.uuid4())
    turns: list[dict] = []
    agent = ReceptionistAgent()
    agent.caller_number = _caller_number(ctx)

    session = AgentSession(
        stt=soniox.STT(params=soniox.STTOptions(model="stt-rt-v4", language_hints=["en"])),
        llm=_build_llm(),
        tts=elevenlabs.TTS(voice_id=settings.elevenlabs_voice_id, model="eleven_multilingual_v2"),
        vad=silero.VAD.load(),
    )

    @session.on("conversation_item_added")
    def _on_item(event) -> None:  # noqa: ANN001 — SDK event object
        item = getattr(event, "item", event)
        role = getattr(item, "role", "agent")
        text = getattr(item, "text_content", None) or getattr(item, "content", "") or ""
        turns.append(
            {"role": "agent" if role == "assistant" else "customer", "text": str(text), "ts": 0}
        )

    async def _post_call() -> None:
        payload = {
            "call_session_id": call_session_id,
            "direction": "inbound",
            "from_number": agent.caller_number or _caller_number(ctx),
            "provider_call_id": ctx.room.name,
            "transcript": turns,
            "booking": agent.booking,
            "message": agent.message,
            "opted_out": agent.opted_out,
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{WEBHOOK_BASE}/api/v2/webhooks/livekit", json=payload)
        except Exception:  # noqa: BLE001 — never block shutdown on the post
            pass

    ctx.add_shutdown_callback(_post_call)

    await session.start(agent=agent, room=ctx.room, room_options=room_io.RoomOptions())
    await session.generate_reply(
        instructions=f"Greet the caller warmly as {CLINIC}, say you're an automated assistant "
        "and the call may be recorded, then ask how you can help."
    )


def main() -> None:
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
