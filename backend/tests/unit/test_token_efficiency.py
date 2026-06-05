"""Token-efficiency logic (PRD §19): trim, no-LLM short-circuit, single-call summary."""

from callwise.domain.verification import (
    CALL_VERIFICATION_SCHEMA,
    trim_turns,
    verify_transcript,
)
from callwise.providers.llm.mock import MockLLMProvider


class _BoomLLM:
    """Fails loudly if the LLM is called — proves the short-circuit spends no tokens."""

    async def complete_json(self, **_):
        raise AssertionError("LLM must not be called when there is no customer speech")

    async def summarize(self, text, *, language="en"):
        raise AssertionError("summarize must not be called")


def test_trim_caps_number_of_turns():
    turns = [{"role": "customer", "text": f"turn {i}"} for i in range(100)]
    trimmed = trim_turns(turns)
    assert len(trimmed) == 40  # default transcript_max_turns


def test_trim_caps_chars_per_turn():
    trimmed = trim_turns([{"role": "customer", "text": "x" * 5000}])
    assert len(trimmed[0]["text"]) == 600  # default transcript_max_chars_per_turn


async def test_no_customer_speech_short_circuits_without_llm():
    turns = [{"role": "agent", "text": "Hello, are you there?"}]
    result = await verify_transcript(_BoomLLM(), expected={}, turns=turns, language="en")
    assert result["outcome"] == "undetermined"
    assert result["confidence"] == 0.0


async def test_customer_speech_runs_single_call_with_summary():
    result = await verify_transcript(
        MockLLMProvider(),
        expected={},
        turns=[{"role": "customer", "text": "Please book a Saturday appointment."}],
        language="en",
    )
    assert result["outcome"] == "appointment_booked"
    assert "summary" in result  # summary comes from the SAME call — no separate request


def test_schema_requires_summary_field():
    schema = CALL_VERIFICATION_SCHEMA["schema"]
    assert "summary" in schema["required"]
    assert "summary" in schema["properties"]
