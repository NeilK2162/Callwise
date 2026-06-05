"""Fixtures for the DB-backed idempotency suite.

Connects to `DATABASE_URL_DIRECT` (CI provides a Postgres service container; locally point
it at the docker-compose Postgres and set `CALLWISE_IT_DB=1`). Schema is created from the
model metadata. Tests are skipped entirely when `CALLWISE_IT_DB` is unset.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import callwise.db.models  # noqa: F401  (populate Base.metadata)
from callwise.config import get_settings
from callwise.db.base import Base

requires_db = pytest.mark.skipif(
    not os.getenv("CALLWISE_IT_DB"),
    reason="integration DB not configured (set CALLWISE_IT_DB)",
)


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        get_settings().database_url_direct, connect_args={"statement_cache_size": 0}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # idempotent (checkfirst)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()
