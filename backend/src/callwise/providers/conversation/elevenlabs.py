"""ElevenLabs ConvAI adapter (SIP) — default conversation layer for scale.

ElevenLabs bridges PSTN ↔ ConvAI agent. We inject per-call dynamic variables via the
call-context endpoint (keyed on call_session_id) and receive the conversation back as an
HMAC-signed `post_call_transcription` webhook. We don't run the audio loop ourselves.

post_call_transcription payload (per docs):
    { type, event_timestamp, data: {
        agent_id, conversation_id, status,
        transcript: [{ role: "agent"|"user", message, time_in_call_secs }],
        metadata: { call_duration_secs, ... },
        analysis: { transcript_summary, data_collection_results, ... },
        conversation_initiation_client_data: { dynamic_variables: {...} } } }
Ref: elevenlabs.io/docs/agents-platform/workflows/post-call-webhooks
"""

from __future__ import annotations

from typing import Any

from callwise.config import Settings
from callwise.domain.snapshots import CallContextSnapshot
from callwise.providers.conversation.base import ConversationProvider, ParsedCall


def _dynamic_variables(raw: dict) -> dict:
    return (
        (raw.get("data", {}) or {})
        .get("conversation_initiation_client_data", {})
        .get("dynamic_variables", {})
        or {}
    )


def session_id_from_payload(raw: dict) -> str | None:
    """Our call_session_id round-trips via the dynamic variable we injected at call start."""
    sid = _dynamic_variables(raw).get("call_session_id")
    return str(sid) if sid else None


class ElevenLabsProvider(ConversationProvider):
    name = "elevenlabs"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def build_context(self, snapshot: CallContextSnapshot) -> dict:
        # Dynamic variables ElevenLabs injects into the agent prompt at call time. The
        # call-context endpoint adds `call_session_id` so the post-call webhook correlates
        # back to this session (see webhook_ingest/routers/context.py).
        return {
            **snapshot.dynamic_variables,
            "customer_name": snapshot.customer_name or "",
            "language": snapshot.language,
            "agent_id": snapshot.agent_id or self._settings.elevenlabs_agent_id or "",
        }

    def parse_post_call(self, raw: dict) -> ParsedCall:
        data: dict[str, Any] = raw.get("data", {}) or {}
        turns: list[dict] = []
        for turn in data.get("transcript", []) or []:
            role = "agent" if turn.get("role") == "agent" else "customer"
            turns.append(
                {
                    "role": role,
                    "text": turn.get("message", ""),
                    "ts": turn.get("time_in_call_secs", 0),
                }
            )
        metadata = data.get("metadata", {}) or {}
        analysis = data.get("analysis", {}) or {}
        return ParsedCall(
            turns=turns,
            recording_url=None,  # audio arrives via a separate post_call_audio webhook
            summary=analysis.get("transcript_summary"),
            provider_call_id=data.get("conversation_id"),
            duration_s=metadata.get("call_duration_secs"),
        )
