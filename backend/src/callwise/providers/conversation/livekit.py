"""LiveKit real-time agent adapter — STUB.

Full-control path: Soniox STT → LLM → ElevenLabs TTS inside a ScriptEngine FSM, for
deterministic slot-filling, custom barge-in, or on-prem audio. Higher operational cost;
reserved for clients who need it. Owns the mutable `ConversationState` (domain.state),
checkpointed to Redis so a worker restart recovers an active call.
"""

from __future__ import annotations

from callwise.config import Settings
from callwise.domain.snapshots import CallContextSnapshot
from callwise.providers.conversation.base import ConversationProvider, ParsedCall


class LiveKitProvider(ConversationProvider):
    name = "livekit"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def build_context(self, snapshot: CallContextSnapshot) -> dict:
        return {
            "script_flow_id": snapshot.script_flow_id,
            "allowed_actions": snapshot.allowed_actions,
            **snapshot.dynamic_variables,
        }

    def parse_post_call(self, raw: dict) -> ParsedCall:
        # TODO: assemble transcript from the FSM turn log persisted during the call.
        raise NotImplementedError("LiveKit transcript assembly not yet implemented")
