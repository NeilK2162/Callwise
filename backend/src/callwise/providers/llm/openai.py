"""OpenAI adapter (Structured Outputs). Requires the optional `llm` extra."""

from __future__ import annotations

from typing import Any

from callwise.config import Settings
from callwise.providers.llm import _openai_common as core
from callwise.providers.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        from openai import AsyncOpenAI

        self._s = settings
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        self._summarize_model = settings.openai_summarize_model

    async def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_retries: int = 1
    ) -> dict[str, Any]:
        return await core.complete_json(
            self._client, self._model, system=system, user=user, schema=schema, max_retries=max_retries
        )

    async def summarize(self, text: str, *, language: str = "en") -> str:
        return await core.summarize(self._client, self._summarize_model, text)
