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
    """Generic bare-body HMAC-SHA256 check (for providers that sign the raw body).
    Accepts either a bare hex digest or a `t=...,v0=<hex>`-prefixed signature."""
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature.split("v0=")[-1].split(",")[0].strip() if signature else ""
    return _constant_time_eq(expected, provided)


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
    """Validate X-Twilio-Signature for a form-encoded callback (Twilio docs §Security):
    base64(HMAC-SHA1(auth_token, url + concat(sorted POST params as name+value))).
    `url` must be the exact public webhook URL Twilio called."""
    import base64
    from urllib.parse import parse_qsl

    s = get_settings()
    if not s.twilio_auth_token:
        if s.app_env == "dev":
            log.warning("webhook_hmac_skipped_dev", provider="twilio")
            return True
        return False
    if not signature_header:
        return False

    params = parse_qsl(raw_body.decode("utf-8"), keep_blank_values=True)
    signed = url + "".join(f"{k}{v}" for k, v in sorted(params))
    digest = hmac.new(s.twilio_auth_token.encode(), signed.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    return _constant_time_eq(expected, signature_header)


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
