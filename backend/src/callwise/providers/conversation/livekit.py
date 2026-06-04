"""LiveKit real-time agent adapter — the full-control conversation path (PRD §5.4).

Soniox STT → LLM → ElevenLabs TTS inside a LiveKit AgentSession, for deterministic
slot-filling, custom barge-in, or on-prem audio. The agent itself runs as a separate
deployable process (see `livekit_agent.py`); when a call ends it POSTs a normalized
post-call payload to our `/api/v2/webhooks/livekit` endpoint:

    { "call_session_id": "...", "transcript": [{"role","text","ts"}],
      "summary": "...", "duration_s": 123, "recording_url": "..." }

This adapter owns the per-call context injected at session start and the parsing of that
post-call payload. Grounded in the LiveKit Agents SDK + Soniox/ElevenLabs plugin docs.
"""

from __future__ import annotations

from callwise.config import Settings
from callwise.domain.snapshots import CallContextSnapshot
from callwise.providers.conversation.base import ConversationProvider, ParsedCall


def session_id_from_payload(raw: dict) -> str | None:
    sid = raw.get("call_session_id")
    return str(sid) if sid else None


class LiveKitProvider(ConversationProvider):
    name = "livekit"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def build_context(self, snapshot: CallContextSnapshot) -> dict:
        # Dynamic variables handed to the LiveKit agent at session start (via the
        # call-context endpoint). The FSM/script uses script_flow_id + allowed_actions.
        return {
            "script_flow_id": snapshot.script_flow_id or "",
            "allowed_actions": snapshot.allowed_actions,
            "customer_name": snapshot.customer_name or "",
            "language": snapshot.language,
            **snapshot.dynamic_variables,
        }

    def parse_post_call(self, raw: dict) -> ParsedCall:
        turns = [
            {"role": t.get("role", "agent"), "text": t.get("text", ""), "ts": t.get("ts", 0)}
            for t in (raw.get("transcript") or [])
        ]
        return ParsedCall(
            turns=turns,
            recording_url=raw.get("recording_url"),
            summary=raw.get("summary"),
            provider_call_id=raw.get("provider_call_id") or raw.get("call_session_id"),
            duration_s=raw.get("duration_s"),
        )
