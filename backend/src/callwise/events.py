"""Real-time fan-out over Redis pub/sub (PRD §11.1, §18.1 "the query appears").

Workers publish card-update events to a per-owner channel; any control-api replica with a
connected dashboard websocket subscribes and forwards. This is how a new query card slides
into the feed in real time as a call completes.
"""

from __future__ import annotations

import uuid

import orjson
from redis.asyncio import Redis


def feed_channel(owner_id: uuid.UUID | str) -> str:
    return f"events:{owner_id}"


async def publish_card_event(redis: Redis, owner_id: uuid.UUID | str, payload: dict) -> None:
    await redis.publish(feed_channel(owner_id), orjson.dumps(payload))
