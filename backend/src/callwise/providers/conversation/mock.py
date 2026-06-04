"""Mock conversation provider — produces a believable, scenario-matched transcript.

The transcript is shaped by the simulated `scenario` so the (mock) LLM verifier classifies
it consistently — the same end-to-end path a real transcript would take.
"""

from __future__ import annotations

from callwise.domain.snapshots import CallContextSnapshot
from callwise.providers.conversation.base import ConversationProvider, ParsedCall

_SCENARIOS: dict[str, tuple[list[dict], str]] = {
    "appointment_booked": (
        [
            {"role": "agent", "text": "Thanks for calling Bright Smile Dental! How can I help?", "ts": 0},
            {"role": "customer", "text": "How much is a root canal, and is there a Saturday slot?", "ts": 4},
            {"role": "agent", "text": "It starts at 6,000. The earliest Saturday is 11 AM.", "ts": 9},
            {"role": "customer", "text": "Please book that Saturday appointment.", "ts": 14},
            {"role": "agent", "text": "Booked for Saturday 11 AM. Confirmation sent by SMS.", "ts": 17},
        ],
        "Booked a root canal appointment for Saturday 11 AM. Confirmed via SMS.",
    ),
    "callback_needed": (
        [
            {"role": "agent", "text": "Bright Smile Dental, how can I help?", "ts": 0},
            {"role": "customer", "text": "I'm busy now — can you call me back tomorrow morning?", "ts": 5},
            {"role": "agent", "text": "Of course — we'll call you back tomorrow morning.", "ts": 10},
        ],
        "Customer requested a callback tomorrow morning to reschedule.",
    ),
    "not_interested": (
        [
            {"role": "agent", "text": "Hi, this is Bright Smile Dental with a check-up reminder.", "ts": 0},
            {"role": "customer", "text": "I'm not interested right now, thank you.", "ts": 4},
            {"role": "agent", "text": "No problem, have a great day.", "ts": 7},
        ],
        "Customer not interested in a check-up at this time.",
    ),
    "question_answered": (
        [
            {"role": "agent", "text": "Bright Smile Dental, how can I help?", "ts": 0},
            {"role": "customer", "text": "What are your opening hours on weekdays?", "ts": 4},
            {"role": "agent", "text": "We're open 9 AM to 6 PM, Monday to Friday.", "ts": 8},
            {"role": "customer", "text": "Great, thanks.", "ts": 11},
        ],
        "Answered a question about weekday opening hours.",
    ),
}


class MockConversationProvider(ConversationProvider):
    name = "mock"

    async def build_context(self, snapshot: CallContextSnapshot) -> dict:
        return {
            "customer_name": snapshot.customer_name or "there",
            "language": snapshot.language,
            **snapshot.dynamic_variables,
        }

    def parse_post_call(self, raw: dict) -> ParsedCall:
        scenario = raw.get("scenario", "question_answered")
        turns, summary = _SCENARIOS.get(scenario, _SCENARIOS["question_answered"])
        return ParsedCall(
            turns=turns,
            recording_url=raw.get("recording_url"),
            summary=summary,
            provider_call_id=raw.get("provider_call_id"),
            duration_s=raw.get("duration_s", 90),
        )
