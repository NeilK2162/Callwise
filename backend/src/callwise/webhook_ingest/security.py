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


# ElevenLabs signs webhooks Stripe-style: header `ElevenLabs-Signature: t=<unix>,v0=<hex>`,
# where <hex> = HMAC-SHA256(secret, f"{t}.{raw_body}"). Timestamp tolerance is 30 minutes.
# Refs: elevenlabs.io/docs/.../post-call-webhooks (SDK construct_event does the same).
_ELEVENLABS_TOLERANCE_S = 30 * 60


def _parse_signature_header(header: str) -> tuple[str | None, str | None]:
    t = v0 = None
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            t = value
        elif key == "v0":
            v0 = value
    return t, v0


def verify_elevenlabs(raw_body: bytes, signature_header: str | None) -> bool:
    s = get_settings()
    secret = s.elevenlabs_webhook_secret
    if not secret:
        # Only allowed in dev. Never skip verification in staging/prod.
        if s.app_env == "dev":
            log.warning("webhook_hmac_skipped_dev", provider="elevenlabs")
            return True
        return False
    if not signature_header:
        return False
    t, v0 = _parse_signature_header(signature_header)
    if not t or not v0:
        return False
    try:
        if abs(time.time() - int(t)) > _ELEVENLABS_TOLERANCE_S:
            return False  # stale → replay defense
    except ValueError:
        return False
    signed = t.encode() + b"." + raw_body  # exact byte layout of the raw body matters
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return _constant_time_eq(expected, v0)


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
