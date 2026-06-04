"""Async SQLAlchemy engine + session, configured to be safe behind PgBouncer.

Critical production footgun (PRD §9.7): behind PgBouncer in **transaction** pooling
mode, asyncpg's prepared-statement cache corrupts the protocol because a connection is
not pinned to one client across statements. We therefore set `statement_cache_size=0`.
Per-process pools stay small because PgBouncer multiplexes thousands of clients onto a
few real Postgres connections.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from callwise.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


@lru_cache
def get_engine() -> AsyncEngine:
    s = get_settings()
    return create_async_engine(
        s.database_url,
        pool_size=s.db_pool_size,
        max_overflow=s.db_max_overflow,
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},  # REQUIRED behind PgBouncer txn mode
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(), expire_on_commit=False, autoflush=False
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency / context manager yielding a scoped session."""
    async with get_sessionmaker()() as session:
        yield session
