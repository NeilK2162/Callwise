"""WebSocket event + live-transcript streams (PRD §11.1).

The dashboard subscribes here so a new query card slides into the feed in real time as a
call completes (the demo's "the query appears" moment, PRD §18.1). Fan-out is backed by a
Redis pub/sub channel so any control-api replica can push to any connected client.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from callwise.logging import get_logger

router = APIRouter()
log = get_logger(__name__)


@router.websocket("/ws")
async def ws_events(websocket: WebSocket) -> None:
    await websocket.accept()
    # TODO: authenticate via query-param token; subscribe to Redis `events:{owner_id}` and
    #       forward messages. For now this is a keepalive echo so the client can connect.
    try:
        while True:
            msg = await websocket.receive_text()
            await websocket.send_json({"echo": msg})
    except WebSocketDisconnect:
        log.info("ws_disconnected")


@router.websocket("/ws/transcripts")
async def ws_transcripts(websocket: WebSocket) -> None:
    await websocket.accept()
    # TODO: stream live transcript turns for an in-progress call (LiveKit path).
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log.info("ws_transcripts_disconnected")
