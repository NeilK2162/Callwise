"""Azure OpenAI adapter (default for production) — STUB.

Throttled by a token-budget limiter on the verification workers so a verification surge
can't blow the deployment's TPM quota; excess queues (PRD §8.4). Use multiple deployments
to raise the ceiling. Requires the optional `llm` extra.
"""

from __future__ import annotations

from typing import Any

from callwise.config import Settings
from callwise.providers.llm.base import LLMProvider


class AzureOpenAIProvider(LLMProvider):
    name = "azure_openai"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # from openai import AsyncAzureOpenAI
        # self._client = AsyncAzureOpenAI(azure_endpoint=..., api_key=..., api_version=...)

    async def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_retries: int = 1
    ) -> dict[str, Any]:
        # TODO: response_format={"type": "json_schema", "json_schema": schema};
        #       one repair pass on parse failure; return parsed dict.
        raise NotImplementedError("Azure OpenAI adapter not yet implemented")

    async def summarize(self, text: str, *, language: str = "en") -> str:
        raise NotImplementedError("Azure OpenAI adapter not yet implemented")
