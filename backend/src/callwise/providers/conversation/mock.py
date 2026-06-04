"""Mock conversation provider — produces a believable transcript for local dev/demo."""

from __future__ import annotations

from callwise.domain.snapshots import CallContextSnapshot
from callwise.providers.conversation.base import ConversationProvider, ParsedCall


class MockConversationProvider(ConversationProvider):
    name = "mock"

    async def build_context(self, snapshot: CallContextSnapshot) -> dict:
        return {
            "customer_name": snapshot.customer_name or "there",
            "language": snapshot.language,
            **snapshot.dynamic_variables,
        }

    def parse_post_call(self, raw: dict) -> ParsedCall:
        name = raw.get("customer_name", "there")
        return ParsedCall(
            turns=[
                {"role": "agent", "text": f"Hi {name}, this is the clinic assistant.", "ts": 0},
                {"role": "customer", "text": "Yes, I wanted to ask about a booking.", "ts": 3},
                {"role": "agent", "text": "I can help with that. What day works?", "ts": 6},
                {"role": "customer", "text": "Saturday morning if possible.", "ts": 9},
                {"role": "agent", "text": "Booked you for Saturday 11 AM. Confirmed!", "ts": 12},
            ],
            recording_url=raw.get("recording_url"),
            summary="Booked appointment for Saturday 11 AM.",
            provider_call_id=raw.get("provider_call_id"),
            duration_s=raw.get("duration_s", 112),
        )
