import uuid

from callwise.control_api.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from callwise.webhook_ingest.security import sign_context_token, verify_context_token


def test_password_hash_roundtrip():
    h = hash_password("s3cret-password")
    assert verify_password("s3cret-password", h)
    assert not verify_password("wrong", h)


def test_access_token_roundtrip():
    uid = str(uuid.uuid4())
    payload = decode_token(create_access_token(uid))
    assert payload["sub"] == uid
    assert payload["type"] == "access"


def test_context_token_valid_and_invalid():
    sid = str(uuid.uuid4())
    assert verify_context_token(sign_context_token(sid)) == sid
    assert verify_context_token("not-a-real-token") is None
