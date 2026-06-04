"""Webhook security (PRD §14.3, §14.4).

Everything here runs **before** any processing: HMAC verification rejects forgeries, a
timestamp-tolerance window + the `processed_events` dedup defeat replay, and the
call-context endpoint is guarded by a short-lived signed token rather than relying on an
unguessable URL (the hardening of the legacy unauthenticated bridge, §14.4).
"""

from __future__ import annotations

import hashlib
import hmac
import time

import jwt

from callwise.config import get_settings
from callwise.logging import get_logger

log = get_logger(__name__)


def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def verify_hmac_sha256(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    # Accept either bare hex or `t=...,v0=...`-style prefixed signatures.
    provided = signature.split("v0=")[-1].split(",")[0].strip() if signature else ""
    return _constant_time_eq(expected, provided)


def verify_elevenlabs(raw_body: bytes, signature_header: str | None) -> bool:
    s = get_settings()
    if not s.elevenlabs_webhook_secret:
        # Only allowed in dev (mock provider). Never skip verification in staging/prod.
        if s.app_env == "dev":
            log.warning("webhook_hmac_skipped_dev", provider="elevenlabs")
            return True
        return False
    if not signature_header:
        return False
    return verify_hmac_sha256(raw_body, signature_header, s.elevenlabs_webhook_secret)


def verify_twilio(raw_body: bytes, signature_header: str | None, url: str) -> bool:
    # TODO: Twilio uses HMAC-SHA1 over the full URL + sorted POST params, base64-encoded.
    #       Implement with the auth token; reject in non-dev until done.
    s = get_settings()
    if s.app_env == "dev":
        log.warning("webhook_hmac_skipped_dev", provider="twilio")
        return True
    return False


def within_timestamp_tolerance(event_ts: float) -> bool:
    tol = get_settings().webhook_timestamp_tolerance_seconds
    return abs(time.time() - event_ts) <= tol


# --- Short-lived signed context token (PRD §14.4) ---
def sign_context_token(call_session_id: str) -> str:
    s = get_settings()
    now = int(time.time())
    return jwt.encode(
        {"sid": call_session_id, "iat": now, "exp": now + s.context_token_ttl_seconds},
        s.context_token_secret,
        algorithm="HS256",
    )


def verify_context_token(token: str) -> str | None:
    """Return the call_session_id if the token is valid and unexpired, else None."""
    try:
        payload = jwt.decode(
            token, get_settings().context_token_secret, algorithms=["HS256"]
        )
    except Exception:  # noqa: BLE001
        return None
    return payload.get("sid")
