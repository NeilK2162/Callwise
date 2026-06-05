"""WebSocket event + live-transcript streams (PRD §11.1, §18.1).

The dashboard subscribes here so a new query card slides into the feed in real time as a
call completes. Fan-out is backed by a Redis pub/sub channel (`events:{owner_id}`), so any
control-api replica can push to any connected client. Auth is via a query-param token
(browsers can't attach Authorization headers to a WebSocket handshake).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from callwise.control_api.security import decode_token
from callwise.events import feed_channel, transcript_channel
from callwise.logging import get_logger
from callwise.redis_pool import get_redis

router = APIRouter()
log = get_logger(__name__)


@router.websocket("/ws")
async def ws_events(websocket: WebSocket, token: str | None = None) -> None:
    if not token:
        await websocket.close(code=4401)
        return
    try:
        owner_id = decode_token(token)["sub"]
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401)
        return

    await websocket.accept()
    redis = get_redis()
    pubsub = redis.pubsub()
    channel = feed_channel(owner_id)
    await pubsub.subscribe(channel)

    async def pump_to_client() -> None:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message["data"]
            await websocket.send_text(data.decode() if isinstance(data, bytes) else data)

    async def drain_client() -> None:
        # We don't process inbound messages; this just detects disconnect.
        while True:
            await websocket.receive_text()

    pump = asyncio.create_task(pump_to_client())
    drain = asyncio.create_task(drain_client())
    try:
        await asyncio.wait({pump, drain}, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for task in (pump, drain):
            task.cancel()
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass
        log.info("ws_closed", owner=owner_id)


@router.websocket("/ws/transcripts")
async def ws_transcripts(
    websocket: WebSocket, token: str | None = None, session_id: str | None = None
) -> None:
    """Stream live transcript turns for an in-progress call (LiveKit path publishes to the
    `transcript:{session_id}` Redis channel)."""
    if not token or not session_id:
        await websocket.close(code=4401)
        return
    try:
        decode_token(token)
    except Exception:  # noqa: BLE001
        await websocket.close(code=4401)
        return

    await websocket.accept()
    pubsub = get_redis().pubsub()
    channel = transcript_channel(session_id)
    await pubsub.subscribe(channel)

    async def pump() -> None:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message["data"]
            await websocket.send_text(data.decode() if isinstance(data, bytes) else data)

    async def drain() -> None:
        while True:
            await websocket.receive_text()

    pump_task = asyncio.create_task(pump())
    drain_task = asyncio.create_task(drain())
    try:
        await asyncio.wait({pump_task, drain_task}, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for task in (pump_task, drain_task):
            task.cancel()
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass
        log.info("ws_transcripts_closed", session=session_id)
