"""Mock LLM — deterministic verification output for local dev, demo, and tests."""

from __future__ import annotations

from typing import Any

from callwise.providers.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    name = "mock"

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_retries: int = 1,
    ) -> dict[str, Any]:
        # Naive heuristic so demo data looks plausible without a real model.
        text = user.lower()
        if "book" in text or "saturday" in text or "appointment" in text:
            outcome = "appointment_booked"
        elif "call me back" in text or "callback" in text:
            outcome = "callback_needed"
        elif "not interested" in text:
            outcome = "not_interested"
        else:
            outcome = "question_answered"
        return {
            "outcome": outcome,
            "responder_type": "human",
            "confidence": 0.92,
            "extracted": {"service": "root canal", "date": "Sat 11AM"},
        }

    async def summarize(self, text: str, *, language: str = "en") -> str:
        return "Customer enquiry handled; appointment booked and confirmed via SMS."
