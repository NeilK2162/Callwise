"""Azure OpenAI adapter (Structured Outputs) — default for production.

Throttled by a token-budget limiter on the verification workers so a surge can't blow the
deployment's TPM quota (PRD §8.4). Use multiple deployments to raise the ceiling. Requires
the optional `llm` extra.
"""

from __future__ import annotations

from typing import Any

from callwise.config import Settings
from callwise.providers.llm import _openai_common as core
from callwise.providers.llm.base import LLMProvider


class AzureOpenAIProvider(LLMProvider):
    name = "azure_openai"

    def __init__(self, settings: Settings) -> None:
        from openai import AsyncAzureOpenAI

        self._s = settings
        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint or "",
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        # On Azure, the "model" is the deployment name.
        self._model = settings.azure_openai_deployment or "gpt-4o"

    async def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_retries: int = 1
    ) -> dict[str, Any]:
        return await core.complete_json(
            self._client, self._model, system=system, user=user, schema=schema, max_retries=max_retries
        )

    async def summarize(self, text: str, *, language: str = "en") -> str:
        return await core.summarize(self._client, self._model, text)
