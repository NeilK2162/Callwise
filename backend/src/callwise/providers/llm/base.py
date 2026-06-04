"""LLM interface (PRD §1.1, §7.3).

Behind a factory: Azure OpenAI (default), OpenAI, Anthropic. `complete_json` enforces a
strict JSON schema with one repair pass on parse failure; the verifier never crashes the
worker on bad JSON — it falls back to `undetermined` + DLQ (edge case #24).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_retries: int = 1,
    ) -> dict[str, Any]:
        """Return a dict conforming to `schema`. One repair pass on parse failure."""

    @abstractmethod
    async def summarize(self, text: str, *, language: str = "en") -> str:
        """One-shot summary (cheaper model than verification, PRD §15.6)."""
