from callwise.domain.verification import (
    CALL_VERIFICATION_SCHEMA,
    CONFIDENCE_AUTO_APPLY_THRESHOLD,
    build_verify_prompt,
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


def test_build_verify_prompt_scopes_to_one_customer():
    prompt = build_verify_prompt(
        expected={"service": "root canal"},
        turns=[{"role": "customer", "text": "Saturday please"}],
        language="en",
    )
    assert "this customer only" in prompt.lower()
    assert "root canal" in prompt
    assert "[customer]" in prompt


def test_build_verify_prompt_empty_transcript_marker():
    prompt = build_verify_prompt(expected={}, turns=[], language="hi")
    assert "no transcript produced" in prompt


def test_confidence_threshold_blocks_auto_apply():
    assert CONFIDENCE_AUTO_APPLY_THRESHOLD == 0.6
