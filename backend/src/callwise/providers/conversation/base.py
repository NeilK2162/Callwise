"""Conversation layer interface (PRD §5.4).

Two interchangeable implementations behind one interface:
  * **ElevenLabs ConvAI (SIP, default for scale):** the provider bridges PSTN ↔ agent and
    holds turn-by-turn state; we inject the per-call context snapshot and receive the
    final transcript.
  * **LiveKit real-time agent (full control):** Soniox STT → LLM → TTS in a ScriptEngine
    FSM, for deterministic slot-filling / custom barge-in.

Both receive an immutable context snapshot at call start and emit a transcript + turns at
call end.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from callwise.domain.snapshots import CallContextSnapshot


@dataclass(slots=True)
class ParsedCall:
    """Normalized result of a provider post-call payload."""

    turns: list[dict] = field(default_factory=list)  # [{role, text, ts}, ...]
    recording_url: str | None = None
    summary: str | None = None
    provider_call_id: str | None = None
    duration_s: int | None = None


class ConversationProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def build_context(self, snapshot: CallContextSnapshot) -> dict:
        """Dynamic variables injected into the agent for this session (call-context endpoint)."""

    @abstractmethod
    def parse_post_call(self, raw: dict) -> ParsedCall:
        """Normalize a provider post-call webhook payload into our turn schema."""
