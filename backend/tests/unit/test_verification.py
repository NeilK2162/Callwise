from callwise.domain.verification import (
    CALL_VERIFICATION_SCHEMA,
    verify_transcript,
)
from callwise.providers.llm.mock import MockLLMProvider


async def test_empty_transcript_is_undetermined_without_llm_call():
    result = await verify_transcript(
        MockLLMProvider(), expected={}, turns=[], language="en"
    )
    assert result["outcome"] == "undetermined"
    assert result["confidence"] == 0.0


async def test_booking_intent_classified():
    turns = [{"role": "customer", "text": "Can I book a Saturday appointment?"}]
    result = await verify_transcript(
        MockLLMProvider(), expected={"service": "root canal"}, turns=turns, language="en"
    )
    assert result["outcome"] == "appointment_booked"
    assert 0.0 <= result["confidence"] <= 1.0


def test_schema_enumerates_all_outcomes():
    enum = CALL_VERIFICATION_SCHEMA["schema"]["properties"]["outcome"]["enum"]
    assert "appointment_booked" in enum
    assert "undetermined" in enum
