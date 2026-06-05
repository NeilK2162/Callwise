"""Shared OpenAI-style logic for the OpenAI and Azure OpenAI adapters (PRD §7.3, §19).

Structured Outputs via Chat Completions `response_format={"type":"json_schema",...}`. Cost
controls: the static system+schema prefix is sent first so the provider auto-caches it
(prompt caching); output is capped at `max_tokens`; `response.usage` is metered; and a
**cheap-first / escalate-on-low-confidence** cascade keeps the common case cheap while
preserving accuracy on the uncertain minority. A refusal (`message.refusal`) or a parse
failure (after one repair pass) falls back to `{}` so the verifier coerces to
`undetermined` rather than crashing the worker (edge #24).
"""

from __future__ import annotations

import json
from typing import Any

from callwise.observability.metrics import LLM_TOKENS_USED


def _response_format(schema: dict[str, Any]) -> dict[str, Any]:
    # strict=False because `extracted` is an open, vertical-specific object; strict mode
    # requires every object be closed (additionalProperties:false + all-required).
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.get("name", "result"),
            "schema": schema.get("schema", schema),
            "strict": False,
        },
    }


def _parse(content: str | None) -> dict[str, Any] | None:
    try:
        parsed = json.loads(content or "")
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _meter(resp: Any) -> None:
    usage = getattr(resp, "usage", None)
    if usage is not None:
        LLM_TOKENS_USED.inc(float(getattr(usage, "total_tokens", 0) or 0))


async def _attempt(
    client: Any, model: str, system: str, user: str, schema: dict[str, Any], max_tokens: int, max_retries: int
) -> dict[str, Any] | None:
    messages = [
        {"role": "system", "content": system},  # static prefix → cached across calls
        {"role": "user", "content": user},
    ]
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        response_format=_response_format(schema),
        temperature=0,
        max_tokens=max_tokens,
    )
    _meter(resp)
    message = resp.choices[0].message
    if getattr(message, "refusal", None):
        return {}
    parsed = _parse(message.content)
    if parsed is not None:
        return parsed
    for _ in range(max_retries):
        repair = await client.chat.completions.create(
            model=model,
            messages=[
                *messages,
                {"role": "assistant", "content": message.content or ""},
                {"role": "user", "content": "That was not valid JSON. Return ONLY JSON matching the schema."},
            ],
            response_format=_response_format(schema),
            temperature=0,
            max_tokens=max_tokens,
        )
        _meter(repair)
        parsed = _parse(repair.choices[0].message.content)
        if parsed is not None:
            return parsed
    return None


async def complete_json(
    client: Any,
    model: str,
    *,
    system: str,
    user: str,
    schema: dict[str, Any],
    max_retries: int = 1,
    max_tokens: int = 400,
    escalation_model: str | None = None,
    escalation_threshold: float = 0.6,
) -> dict[str, Any]:
    parsed = await _attempt(client, model, system, user, schema, max_tokens, max_retries)
    if parsed is None:
        return {}
    # Escalate to the strong model only when the cheap model is unsure (PRD §19.2 #7).
    confidence = parsed.get("confidence")
    if (
        escalation_model
        and isinstance(confidence, int | float)
        and float(confidence) < escalation_threshold
    ):
        strong = await _attempt(client, escalation_model, system, user, schema, max_tokens, max_retries)
        if strong is not None:
            return strong
    return parsed


async def summarize(client: Any, model: str, text: str) -> str:
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Summarize this call in one concise sentence."},
            {"role": "user", "content": text},
        ],
        temperature=0,
        max_tokens=120,
    )
    _meter(resp)
    return resp.choices[0].message.content or ""
