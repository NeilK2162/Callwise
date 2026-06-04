"""Auth endpoints (PRD §11.1, §14.1). Registration is gated by a config flag."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from callwise.config import get_settings
from callwise.control_api.deps import CurrentUser, DbSession
from callwise.control_api.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from callwise.control_api.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from callwise.db.models import User

router = APIRouter()


def _tokens(user_id: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: DbSession) -> TokenResponse:
    if not get_settings().allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "registration disabled")
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    await db.commit()
    return _tokens(str(user.id))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DbSession) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return _tokens(str(user.id))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(refresh_token: str, db: DbSession) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong token type")
    return _tokens(payload["sub"])


@router.post("/logout")
async def logout(user: CurrentUser) -> dict[str, str]:
    # Stateless JWT: real revocation needs a jti denylist in Redis (TODO).
    return {"status": "ok"}
