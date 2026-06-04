"""FastAPI dependencies: DB session, current user, row-level ownership (PRD §14.1).

Row-level ownership is enforced through `owned_or_404` / `scope_to_owner` rather than
ad-hoc per endpoint, so a non-superuser can only ever see their own campaigns/contacts
(edge case #46). This is covered by tests.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from callwise.control_api.security import decode_token
from callwise.db.base import get_sessionmaker
from callwise.db.models import User

_bearer = HTTPBearer(auto_error=True)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    try:
        payload = decode_token(creds.credentials)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong token type")
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


def owned_or_404(resource_owner_id: uuid.UUID, user: User) -> None:
    """Raise 404 (not 403 — don't reveal existence) unless the user owns the resource."""
    if user.is_superuser:
        return
    if resource_owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
