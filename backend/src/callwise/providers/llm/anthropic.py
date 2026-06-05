"""Anthropic (Claude) adapter — structured output + prompt caching (PRD §7.3, §19).

Structured JSON is guaranteed via **tool use**: we expose a single tool whose `input_schema`
is the verification schema and force the model to call it, so the result is always valid
JSON in `tool_use.input` (no repair pass needed). The static system block (instructions +
schema-shaped tool) carries `cache_control: ephemeral`, so the bulk of the prompt is cached
across the thousands of verifications/min — only the per-call transcript is uncached
(the single biggest cost lever). Output is capped and `usage` is metered. Requires the
optional `llm` extra. Ref: docs.anthropic.com (Messages, tool use, prompt caching).
"""

from __future__ import annotations

from typing import Any

from callwise.config import Settings
from callwise.observability.metrics import LLM_TOKENS_USED
from callwise.providers.llm.base import LLMProvider


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        from anthropic import AsyncAnthropic

        self._s = settings
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model
        self._max_tokens = settings.llm_max_output_tokens

    def _meter(self, resp: Any) -> None:
        usage = getattr(resp, "usage", None)
        if usage is not None:
            total = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0)
            LLM_TOKENS_USED.inc(float(total))

    async def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_retries: int = 1
    ) -> dict[str, Any]:
        tool = {
            "name": schema.get("name", "result"),
            "description": "Return the structured verification result.",
            "input_schema": schema.get("schema", schema),
        }
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=0,
            # Static prefix → cached across calls (PRD §19.2 #4).
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": user}],
        )
        self._meter(resp)
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        return {}

    async def summarize(self, text: str, *, language: str = "en") -> str:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=120,
            temperature=0,
            messages=[{"role": "user", "content": f"Summarize this call in one sentence:\n{text}"}],
        )
        self._meter(resp)
        return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
