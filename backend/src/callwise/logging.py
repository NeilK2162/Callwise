"""Structured JSON logging with correlation context.

Every log line can carry `call_session_id`, `contact_id`, `campaign_id`, `worker_id`,
and `correlation_id` so a single call's entire lifecycle is reconstructable by filtering
on its `call_session_id` (PRD §13.1). Bound context is propagated via contextvars, so it
works correctly across concurrent asyncio tasks without cross-talk.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_configured = False


def configure_logging(level: str = "INFO", *, json: bool = True) -> None:
    """Idempotent logging setup. Call once at process start."""
    global _configured
    if _configured:
        return

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def bind_call_context(**kwargs: Any) -> None:
    """Bind correlation fields for the current task (e.g. call_session_id=...)."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_call_context() -> None:
    structlog.contextvars.clear_contextvars()
