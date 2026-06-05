"""Dynamic context for the conversation agent (PRD §11.2, §14.4).

`/exotel/call-context` returns the per-call dynamic variables ElevenLabs ConvAI injects.
It is guarded by a **short-lived signed token** (not a bare UUID), validated on fetch —
the hardening of the legacy unauthenticated bridge.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from callwise.config import get_settings
from callwise.db.models import CallSession
from callwise.domain.snapshots import load_snapshot
from callwise.providers.conversation.factory import get_conversation_provider
from callwise.webhook_ingest.deps import DbSession
from callwise.webhook_ingest.security import verify_context_token

router = APIRouter()


@router.get("/exotel/call-context")
async def call_context(db: DbSession, token: str = Query(...)) -> dict:
    sid = verify_context_token(token)
    if sid is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired context token")

    sess = await db.get(CallSession, uuid.UUID(sid))
    if sess is None or sess.context_snapshot_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session/context not found")

    snapshot = await load_snapshot(db, sess.context_snapshot_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "context not found")

    provider = get_conversation_provider()
    context = await provider.build_context(snapshot)
    # Thread our session id through so the post-call webhook correlates back to this call.
    context["call_session_id"] = sid
    return context


@router.get("/exotel/connect-params")
async def connect_params(db: DbSession, token: str = Query(...)) -> dict:
    """Minimal SIP connect params for the bridge — short keys to stay under the ~200-byte
    header limit (PRD §11.2). Only routing essentials; full context is fetched separately."""
    sid = verify_context_token(token)
    if sid is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired context token")

    sess = await db.get(CallSession, uuid.UUID(sid))
    snapshot = (
        await load_snapshot(db, sess.context_snapshot_id)
        if sess and sess.context_snapshot_id
        else None
    )
    settings = get_settings()
    # Short keys on purpose: s=session, a=agent, l=language.
    return {
        "s": sid,
        "a": (snapshot.agent_id if snapshot else None) or settings.elevenlabs_agent_id or "",
        "l": snapshot.language if snapshot else "en",
    }
