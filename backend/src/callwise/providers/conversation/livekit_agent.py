"""Deployable LiveKit voice agent (Soniox STT → LLM → ElevenLabs TTS).

This is the **full-control** conversation runtime (PRD §5.4). It runs as its own process
on LiveKit (Cloud or self-hosted) and is reached via LiveKit's SIP integration — it is NOT
one of the Callwise worker fleet. When a call ends it POSTs a normalized transcript to the
Callwise webhook-ingest service, which feeds the same verification pipeline as every other
provider.

Run (requires the `conversation` extra + LiveKit/SIP setup):
    SONIOX_API_KEY=... ELEVEN_API_KEY=... LIVEKIT_URL=... LIVEKIT_API_KEY=... \
    LIVEKIT_API_SECRET=... uv run python -m callwise.providers.conversation.livekit_agent start

Grounded in the LiveKit Agents SDK + Soniox/ElevenLabs plugin docs:
  - AgentSession(stt=soniox.STT(...), llm=openai.LLM(...), tts=elevenlabs.TTS(...))
  - soniox: `uv add "livekit-agents[soniox]~=1.5"`, model "stt-rt-v4", SONIOX_API_KEY
  - elevenlabs: `uv add "livekit-agents[elevenlabs]~=1.5"`, ELEVEN_API_KEY
Refs: docs.livekit.io/agents/start/voice-ai, /agents/models/stt/soniox, /agents/models/tts/elevenlabs
"""

from __future__ import annotations

import os

import httpx
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, room_io
from livekit.plugins import elevenlabs, openai, silero, soniox

CALLWISE_WEBHOOK_BASE = os.getenv("BASE_URL", "http://localhost:8001")
AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "callwise-agent")

server = AgentServer()


def _instructions(metadata: dict) -> str:
    name = metadata.get("customer_name") or "the customer"
    return (
        "You are Callwise, a polite, concise AI voice agent for a clinic. "
        "Disclose you are an automated assistant at the start. "
        f"You are speaking with {name}. Confirm their identity before sharing any details. "
        "Help with booking, hours, and FAQs. If asked to stop, acknowledge and end the call."
    )


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: agents.JobContext) -> None:
    # call_session_id + dynamic vars are passed as job metadata at SIP dispatch time
    # (or fetched from the call-context endpoint keyed on call_session_id).
    import json

    metadata: dict = {}
    try:
        metadata = json.loads(ctx.job.metadata or "{}")
    except (ValueError, AttributeError):
        metadata = {}
    call_session_id = metadata.get("call_session_id", ctx.room.name)

    turns: list[dict] = []

    session = AgentSession(
        stt=soniox.STT(params=soniox.STTOptions(model="stt-rt-v4", language_hints=["en"])),
        llm=openai.LLM(model=os.getenv("OPENAI_MODEL", "gpt-4o")),
        tts=elevenlabs.TTS(
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
            model="eleven_multilingual_v2",
        ),
        vad=silero.VAD.load(),
    )

    @session.on("conversation_item_added")
    def _on_item(event) -> None:  # noqa: ANN001 — SDK event type
        item = getattr(event, "item", event)
        role = getattr(item, "role", "agent")
        text = getattr(item, "text_content", None) or getattr(item, "content", "") or ""
        turns.append({"role": "agent" if role == "assistant" else "customer", "text": str(text), "ts": 0})

    async def _post_transcript() -> None:
        payload = {
            "call_session_id": call_session_id,
            "transcript": turns,
            "duration_s": None,
            "provider_call_id": ctx.room.name,
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{CALLWISE_WEBHOOK_BASE}/api/v2/webhooks/livekit", json=payload)
        except Exception:  # noqa: BLE001 — never block shutdown on the post
            pass

    ctx.add_shutdown_callback(_post_transcript)

    await session.start(agent=Agent(instructions=_instructions(metadata)), room=ctx.room,
                        room_options=room_io.RoomOptions())
    await session.generate_reply(instructions="Greet the customer and disclose you are an AI assistant.")


def main() -> None:
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
