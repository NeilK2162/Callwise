"""Shared OpenAI-style logic for the OpenAI and Azure OpenAI adapters.

Uses Structured Outputs via Chat Completions `response_format={"type":"json_schema",...}`
(OpenAI docs: Structured model outputs). A refusal is surfaced on `message.refusal`; on a
parse failure we run one repair pass, then fall back to an empty dict so the verifier
coerces to `undetermined` rather than crashing the worker (PRD §7.3, edge #24).

Prompt-caching note: the static system prompt + schema are sent first so OpenAI/Azure
automatically reuse the cached prefix across the thousands of per-call verifications —
only the transcript differs (PRD §15.6).
"""

from __future__ import annotations

import json
from typing import Any


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


async def complete_json(
    client: Any, model: str, *, system: str, user: str, schema: dict[str, Any], max_retries: int = 1
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": system},  # static prefix → cached
        {"role": "user", "content": user},
    ]
    resp = await client.chat.completions.create(
        model=model, messages=messages, response_format=_response_format(schema), temperature=0
    )
    message = resp.choices[0].message
    if getattr(message, "refusal", None):
        return {}
    parsed = _parse(message.content)
    if parsed is not None:
        return parsed

    # One repair pass.
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
        )
        parsed = _parse(repair.choices[0].message.content)
        if parsed is not None:
            return parsed
    return {}


async def summarize(client: Any, model: str, text: str) -> str:
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Summarize this call in one concise sentence."},
            {"role": "user", "content": text},
        ],
        temperature=0,
    )
    return resp.choices[0].message.content or ""
