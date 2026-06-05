"""Post-call verification (PRD §7.3, §5.5, §19).

The verification LLM receives a tightly-scoped context: **only** this contact's expected
fields + this call's transcript. We never batch multiple customers into one LLM call —
that avoids any chance of attributing one customer's answer to another (edge case #26).
Structured output is enforced via a strict JSON schema + a one-shot repair pass; on
persistent failure the outcome is `undetermined` and the task goes to the DLQ rather than
crashing the worker (edge case #24).

Cost (PRD §19): one call does classification + extraction + the one-line `summary`; the
transcript is trimmed to the decision-relevant turns; calls with no customer speech
short-circuit without spending a token.
"""

from __future__ import annotations

from typing import Any

from callwise.config import get_settings
from callwise.db.enums import VerificationOutcome
from callwise.providers.llm.base import LLMProvider

VERIFY_SYSTEM_PROMPT = (
    "You are a call-outcome verifier. Given the EXPECTED fields for one customer and the "
    "transcript of one call, classify the outcome, extract only fields explicitly supported "
    "by the transcript (never invent a value), and write a one-sentence `summary`. If the "
    "transcript is inconclusive, use outcome='undetermined' with low confidence. Output must "
    "match the provided JSON schema exactly."
)

CALL_VERIFICATION_SCHEMA: dict[str, Any] = {
    "name": "call_verification",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        # `summary` is part of the SAME call — no separate summarization request (PRD §19.2).
        "required": ["outcome", "responder_type", "confidence", "extracted", "summary"],
        "properties": {
            "outcome": {"type": "string", "enum": [o.value for o in VerificationOutcome]},
            "responder_type": {"type": "string", "enum": ["human", "machine", "unknown"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "extracted": {"type": "object"},
            "summary": {"type": "string"},
        },
    },
}

# Below this, never auto-apply — route to a human-review queue (edge case #25).
CONFIDENCE_AUTO_APPLY_THRESHOLD = 0.6


def _undetermined(summary: str) -> dict[str, Any]:
    return {
        "outcome": VerificationOutcome.undetermined.value,
        "responder_type": "unknown",
        "confidence": 0.0,
        "extracted": {},
        "summary": summary,
    }


def trim_turns(turns: list[dict]) -> list[dict]:
    """Trim to the decision-relevant turns + cap per-turn length (PRD §19.2 #6).

    The outcome is almost always decided in the opening and closing turns, so for long
    calls we keep the first 2 and the last (max_turns - 2) turns, and truncate each turn's
    text — cutting input tokens with negligible quality loss."""
    s = get_settings()
    max_turns, max_chars = s.transcript_max_turns, s.transcript_max_chars_per_turn
    if len(turns) > max_turns:
        turns = turns[:2] + turns[-(max_turns - 2):]
    return [{**t, "text": str(t.get("text", ""))[:max_chars]} for t in turns]


def build_verify_prompt(*, expected: dict, turns: list[dict], language: str) -> str:
    lines = [
        f"LANGUAGE: {language}",
        "",
        "EXPECTED FIELDS (this customer only):",
        str(expected),
        "",
        "TRANSCRIPT (this call only):",
    ]
    for turn in turns:
        lines.append(f"  [{turn.get('role', '?')}] {turn.get('text', '')}")
    if not turns:
        lines.append("  (no transcript produced)")
    return "\n".join(lines)


async def verify_transcript(
    llm: LLMProvider, *, expected: dict, turns: list[dict], language: str
) -> dict[str, Any]:
    """Run verification for a single call. Returns a schema-conforming dict.

    Short-circuits **without spending a token** when there is no customer speech to assess
    (empty transcript or agent-only), and trims long transcripts before the call (PRD §19)."""
    meaningful = [t for t in turns if str(t.get("text", "")).strip()]
    customer_turns = [t for t in meaningful if t.get("role") == "customer"]
    if not customer_turns:
        return _undetermined("No customer response captured.")
    return await llm.complete_json(
        system=VERIFY_SYSTEM_PROMPT,
        user=build_verify_prompt(expected=expected, turns=trim_turns(meaningful), language=language),
        schema=CALL_VERIFICATION_SCHEMA,
        max_retries=1,
    )
