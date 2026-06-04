"""Retry classification (PRD §9.3).

**Retryable**: rate-limit, transient 5xx, timeout → re-queue with backoff.
**Terminal**: invalid number, DND/DNC, blacklisted → never retried; contact fails fast.

Misclassifying a terminal error as retryable burns credits in an endless redial loop
(edge case #7); misclassifying a transient one as terminal silently drops a reachable
customer. Keep this list conservative and explicit.
"""

from __future__ import annotations

from enum import StrEnum


class RetryClass(StrEnum):
    retryable = "retryable"
    terminal = "terminal"


# Provider-normalized terminal reasons — these never retry.
TERMINAL_REASONS: frozenset[str] = frozenset(
    {
        "invalid_number",
        "not_in_service",
        "disconnected",
        "dnd",
        "dnc",
        "blacklisted",
        "do_not_contact",
        "opt_out",
        "unallocated_number",
    }
)

# Reasons that warrant a retry with backoff (within attempt limits).
RETRYABLE_REASONS: frozenset[str] = frozenset(
    {
        "rate_limited",
        "no_answer",
        "busy",
        "timeout",
        "provider_5xx",
        "network_error",
        "no_audio",
        "temporary_failure",
    }
)


def classify_reason(reason: str | None) -> RetryClass:
    if reason and reason.lower() in TERMINAL_REASONS:
        return RetryClass.terminal
    # Default unknown errors to terminal — fail safe on cost, surface via DLQ/alerts.
    if reason and reason.lower() in RETRYABLE_REASONS:
        return RetryClass.retryable
    return RetryClass.terminal


def classify_error(exc: BaseException) -> RetryClass:
    """Classify an exception. Import-light: matches on type name + status attrs."""
    name = type(exc).__name__
    if name in {"ProviderRateLimited", "TimeoutError", "ConnectionError"}:
        return RetryClass.retryable
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status, int) and 500 <= status < 600:
        return RetryClass.retryable
    return RetryClass.terminal
