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

import httpx

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


def caller_id_from_payload(raw: dict) -> str | None:
    """The caller's phone number, when the call had one. A real PSTN call carries it as the
    `system__caller_id` dynamic variable; the Twilio-native integration also mirrors it under
    `metadata.phone_call.external_number`. Web/portal test calls have neither (→ None)."""
    cid = _dynamic_variables(raw).get("system__caller_id")
    if cid:
        return str(cid)
    phone_call = ((raw.get("data", {}) or {}).get("metadata", {}) or {}).get("phone_call") or {}
    ext = phone_call.get("external_number")
    return str(ext) if ext else None


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
            recording_url=None,  # audio is fetched out-of-band via fetch_recording()
            summary=analysis.get("transcript_summary"),
            provider_call_id=data.get("conversation_id"),
            duration_s=metadata.get("call_duration_secs"),
        )

    async def fetch_recording(self, provider_call_id: str | None) -> bytes | None:
        """Pull the call audio from the Conversations API (the post-call webhook only flags
        `has_audio`, it doesn't inline the bytes). Best-effort — never blocks verification."""
        api_key = self._settings.elevenlabs_api_key
        if not provider_call_id or not api_key:
            return None
        url = f"https://api.elevenlabs.io/v1/convai/conversations/{provider_call_id}/audio"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers={"xi-api-key": api_key})
            if resp.status_code == 200 and resp.content:
                return resp.content
        except Exception:  # noqa: BLE001 — recording is optional; swallow and move on
            return None
        return None
