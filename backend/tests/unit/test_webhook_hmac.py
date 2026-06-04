"""Webhook HMAC + replay window (PRD §14.3, §14.4)."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from callwise.webhook_ingest.security import (
    verify_hmac_sha256,
    within_timestamp_tolerance,
)


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_hmac_accepts_bare_hex():
    body = b'{"event":"completed"}'
    secret = "test-webhook-secret"
    assert verify_hmac_sha256(body, _sign(body, secret), secret)


def test_valid_hmac_accepts_v0_prefixed_signature():
    body = b'{"event":"completed"}'
    secret = "test-webhook-secret"
    sig = _sign(body, secret)
    assert verify_hmac_sha256(body, f"t=123,v0={sig}", secret)


def test_tampered_body_rejected():
    body = b'{"event":"completed"}'
    secret = "test-webhook-secret"
    assert not verify_hmac_sha256(b'{"event":"tampered"}', _sign(body, secret), secret)


def test_wrong_secret_rejected():
    body = b"payload"
    assert not verify_hmac_sha256(body, _sign(body, "a"), "b")


@pytest.mark.parametrize("delta", [0, 100, 299])
def test_timestamp_within_tolerance(delta, monkeypatch):
    now = 1_700_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)
    assert within_timestamp_tolerance(now - delta) is True


def test_timestamp_outside_tolerance_rejected(monkeypatch):
    now = 1_700_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)
    assert within_timestamp_tolerance(now - 301) is False
