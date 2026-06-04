"""LLM provider factory (PRD §1.1, §7.3)."""

from __future__ import annotations

from callwise.config import LLMProvider as LLMProviderName, Settings, get_settings
from callwise.providers.llm.base import LLMProvider
from callwise.providers.llm.mock import MockLLMProvider


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    match settings.llm_provider:
        case LLMProviderName.mock:
            return MockLLMProvider()
        case LLMProviderName.azure_openai:
            from callwise.providers.llm.azure_openai import AzureOpenAIProvider

            return AzureOpenAIProvider(settings)
        case LLMProviderName.openai:
            from callwise.providers.llm.openai import OpenAIProvider

            return OpenAIProvider(settings)
        case LLMProviderName.anthropic:
            from callwise.providers.llm.anthropic import AnthropicProvider

            return AnthropicProvider(settings)
        case _:
            raise NotImplementedError(
                f"llm provider {settings.llm_provider!r} not wired up"
            )
