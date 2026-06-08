"""Server-tool webhooks for the ElevenLabs Agent (PRD §0.4, §12).

When ElevenLabs orchestrates the call (its hosted LLM + TTS + turn-taking — the fastest path
for the demo), the agent calls these endpoints *mid-conversation* to actually do things:
check availability, book on Cal.com, take a message, honor do-not-contact. They run the exact
same behaviors as the LiveKit in-process agent's `@function_tool` methods (both delegate to
`callwise.agent_tools`), so the orchestrator is swappable without touching booking logic.

Each call's outcome is stashed by `conversation_id`; the post-call webhook
(`/webhooks/elevenlabs`) + verify worker turn the transcript + stashed outcome into the query
card. Auth is a shared secret header — configure the same value as a tool auth header on the
agent in the ElevenLabs portal (`AGENT_TOOLS_SECRET`).
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from callwise import agent_tools
from callwise.config import get_settings
from callwise.logging import get_logger

log = get_logger(__name__)
router = APIRouter()

SecretHeader = Annotated[str | None, Header(alias="X-Callwise-Agent-Secret")]


def _authorize(secret: str | None) -> None:
    expected = get_settings().agent_tools_secret
    if not expected:
        # Dev convenience only — never run the public tool surface unauthenticated in prod.
        if get_settings().app_env == "dev":
            log.warning("agent_tools_secret_skipped_dev")
            return
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "agent tools secret not configured")
    if not secret or not hmac.compare_digest(secret, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid agent tools secret")


class _Base(BaseModel):
    # Bind these to the agent's system variables in the portal so outcomes attach to the call
    # and the desk gets a callback number: conversation_id={{system__conversation_id}},
    # caller_id={{system__caller_id}}.
    conversation_id: str | None = None
    caller_id: str | None = None


class CheckAvailabilityIn(_Base):
    preference: str | None = None


class CheckTimeIn(_Base):
    desired_iso: str


class BookIn(_Base):
    name: str
    email: str
    slot_iso: str


class MessageIn(_Base):
    name: str
    reason: str
    details: str | None = None
    callback_window: str | None = None


class DoNotContactIn(_Base):
    pass


def _response(result: agent_tools.ToolResult) -> dict:
    """The agent reads `say` to speak the result; `data` (e.g. slots) informs the next tool."""
    body: dict = {"say": result.say, "status": result.status}
    if result.data:
        body.update(result.data)
    return body


async def _record(body: _Base, outcome: dict | None) -> None:
    payload = dict(outcome or {})
    if body.caller_id:
        payload.setdefault("caller_id", body.caller_id)
    await agent_tools.stash_outcome(body.conversation_id, payload)


@router.post("/agent-tools/check-availability")
async def check_availability(body: CheckAvailabilityIn, x_secret: SecretHeader = None) -> dict:
    _authorize(x_secret)
    if body.caller_id:
        await _record(body, None)  # capture the callback number early
    return _response(await agent_tools.check_availability(body.preference))


@router.post("/agent-tools/check-time")
async def check_time(body: CheckTimeIn, x_secret: SecretHeader = None) -> dict:
    _authorize(x_secret)
    if body.caller_id:
        await _record(body, None)
    return _response(await agent_tools.check_time(body.desired_iso))


@router.post("/agent-tools/book-appointment")
async def book_appointment(body: BookIn, x_secret: SecretHeader = None) -> dict:
    _authorize(x_secret)
    result = await agent_tools.book_appointment(
        body.name, body.email, body.slot_iso, phone=body.caller_id
    )
    await _record(body, result.outcome)
    return _response(result)


@router.post("/agent-tools/take-message")
async def take_message(body: MessageIn, x_secret: SecretHeader = None) -> dict:
    _authorize(x_secret)
    result = await agent_tools.take_message(
        body.name,
        body.reason,
        details=body.details,
        callback_window=body.callback_window,
        phone=body.caller_id,
    )
    await _record(body, result.outcome)
    return _response(result)


@router.post("/agent-tools/do-not-contact")
async def do_not_contact(body: DoNotContactIn, x_secret: SecretHeader = None) -> dict:
    _authorize(x_secret)
    result = agent_tools.mark_do_not_contact()
    await _record(body, result.outcome)
    return _response(result)
