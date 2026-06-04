"""Normalized provider errors.

Adapters translate provider-specific failures into these so the dialer's retry logic
(`reliability.retry`) stays provider-agnostic.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Generic, retryable-by-default provider failure (transient 5xx, network, timeout)."""

    def __init__(self, message: str, *, reason: str = "temporary_failure") -> None:
        super().__init__(message)
        self.reason = reason


class TerminalProviderError(ProviderError):
    """Permanent failure — never retry (invalid number, DND, blacklisted). Edge case #7."""

    def __init__(self, message: str, *, reason: str = "invalid_number") -> None:
        super().__init__(message, reason=reason)


class ProviderRateLimitedError(ProviderError):
    """Provider returned a rate-limit response — re-queue with backoff, never drop."""

    def __init__(self, message: str, *, retry_after_ms: int = 1000) -> None:
        super().__init__(message, reason="rate_limited")
        self.retry_after_ms = retry_after_ms
