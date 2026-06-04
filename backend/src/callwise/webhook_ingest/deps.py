"""Webhook-ingest dependencies (no JWT — HMAC + IP allowlist instead, PRD §11.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from callwise.db.base import get_sessionmaker
from callwise.queue.base import Queue
from callwise.queue.factory import get_queue


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
QueueDep = Annotated[Queue, Depends(get_queue)]
