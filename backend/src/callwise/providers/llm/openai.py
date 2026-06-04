"""OpenAI adapter — STUB. Requires the optional `llm` extra."""

from __future__ import annotations

from typing import Any

from callwise.config import Settings
from callwise.providers.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # from openai import AsyncOpenAI
        # self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_retries: int = 1
    ) -> dict[str, Any]:
        raise NotImplementedError("OpenAI adapter not yet implemented")

    async def summarize(self, text: str, *, language: str = "en") -> str:
        raise NotImplementedError("OpenAI adapter not yet implemented")
