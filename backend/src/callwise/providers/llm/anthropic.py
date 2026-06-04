"""Anthropic (Claude) adapter — STUB. Requires the optional `llm` extra.

When implemented, use **prompt caching** on the static portion of the verification prompt
(the system prompt + JSON schema + few-shot examples) so only the per-call transcript is
uncached — this is the bulk of the tokens at thousands of verifications/minute and the
single biggest cost lever (PRD §15.6).
"""

from __future__ import annotations

from typing import Any

from callwise.config import Settings
from callwise.providers.llm.base import LLMProvider


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # from anthropic import AsyncAnthropic
        # self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_retries: int = 1
    ) -> dict[str, Any]:
        # TODO: tool-use / structured output for strict JSON; cache_control on the
        #       static system+schema block; one repair pass on parse failure.
        raise NotImplementedError("Anthropic adapter not yet implemented")

    async def summarize(self, text: str, *, language: str = "en") -> str:
        raise NotImplementedError("Anthropic adapter not yet implemented")
