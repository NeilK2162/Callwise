"""Auth primitives: password hashing (argon2) + JWT issue/verify (PRD §14.1)."""

from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from callwise.config import get_settings

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _encode(sub: str, ttl: int, token_type: str, extra: dict[str, Any]) -> str:
    s = get_settings()
    now = int(time.time())
    payload = {
        "sub": sub,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
        **extra,
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_access_token(user_id: str, **extra: Any) -> str:
    return _encode(user_id, get_settings().jwt_access_ttl_seconds, "access", extra)


def create_refresh_token(user_id: str, **extra: Any) -> str:
    return _encode(user_id, get_settings().jwt_refresh_ttl_seconds, "refresh", extra)


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
