"""Post-call verification (PRD §7.3, §5.5).

The verification LLM receives a tightly-scoped context: **only** this contact's expected
fields + this call's transcript. We never batch multiple customers into one LLM call —
that avoids any chance of attributing one customer's answer to another (edge case #26).
Structured output is enforced via a strict JSON schema + a one-shot repair pass; on
persistent failure the outcome is `undetermined` and the task goes to the DLQ rather than
crashing the worker (edge case #24).
"""

from __future__ import annotations

from typing import Any

from callwise.db.enums import VerificationOutcome
from callwise.providers.llm.base import LLMProvider

VERIFY_SYSTEM_PROMPT = (
    "You are a call-outcome verifier. Given the EXPECTED fields for one customer and the "
    "transcript of one call, classify the outcome and extract only fields that are "
    "explicitly supported by the transcript. Never invent a value. If the transcript is "
    "empty or inconclusive, return outcome='undetermined' with low confidence. Output "
    "must match the provided JSON schema exactly."
)

CALL_VERIFICATION_SCHEMA: dict[str, Any] = {
    "name": "call_verification",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["outcome", "responder_type", "confidence", "extracted"],
        "properties": {
            "outcome": {
                "type": "string",
                "enum": [o.value for o in VerificationOutcome],
            },
            "responder_type": {
                "type": "string",
                "enum": ["human", "machine", "unknown"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "extracted": {"type": "object"},
        },
    },
}

# Below this, never auto-apply — route to a human-review queue (edge case #25).
CONFIDENCE_AUTO_APPLY_THRESHOLD = 0.6


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

    On empty transcript, short-circuits to `undetermined` without spending an LLM call.
    """
    if not turns:
        return {
            "outcome": VerificationOutcome.undetermined.value,
            "responder_type": "unknown",
            "confidence": 0.0,
            "extracted": {},
        }
    return await llm.complete_json(
        system=VERIFY_SYSTEM_PROMPT,
        user=build_verify_prompt(expected=expected, turns=turns, language=language),
        schema=CALL_VERIFICATION_SCHEMA,
        max_retries=1,
    )
