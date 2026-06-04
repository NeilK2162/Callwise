"""ElevenLabs ConvAI adapter (SIP) — partial.

Default conversation layer for scale: ElevenLabs bridges PSTN ↔ ConvAI agent. Per-call
dynamic context is injected via the `call-context` endpoint keyed on `call_session_id`.
We don't run the audio loop ourselves. Post-call transcription + audio + failure arrive
as HMAC-signed webhooks (verified in `webhook_ingest.security`).
"""

from __future__ import annotations

from callwise.config import Settings
from callwise.domain.snapshots import CallContextSnapshot
from callwise.providers.conversation.base import ConversationProvider, ParsedCall


class ElevenLabsProvider(ConversationProvider):
    name = "elevenlabs"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def build_context(self, snapshot: CallContextSnapshot) -> dict:
        # Dynamic variables ElevenLabs injects into the agent prompt at call time.
        return {
            "customer_name": snapshot.customer_name or "",
            "language": snapshot.language,
            "agent_id": snapshot.agent_id or self._settings.elevenlabs_agent_id or "",
            **snapshot.dynamic_variables,
        }

    def parse_post_call(self, raw: dict) -> ParsedCall:
        # TODO: map the `post_call_transcription` payload (raw["transcript"], roles, ts,
        #       raw["metadata"]["call_duration_secs"], audio URL) into ParsedCall.
        raise NotImplementedError("ElevenLabs transcript parsing not yet implemented")
