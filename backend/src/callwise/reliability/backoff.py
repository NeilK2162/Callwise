"""Exponential backoff with full jitter + cap (PRD §9.3).

Full jitter spreads a thundering herd of retries (edge case #38) so a mass failure does
not become a self-inflicted DDoS on the provider when everything retries at once.
"""

from __future__ import annotations

import random


def next_backoff(
    attempt: int, *, base: float = 2.0, cap: float = 300.0, jitter: float = 0.3
) -> float:
    """Seconds to wait before the next attempt (attempt is 1-based)."""
    raw = min(cap, base**attempt)
    return raw * (1 - jitter + random.random() * 2 * jitter)
