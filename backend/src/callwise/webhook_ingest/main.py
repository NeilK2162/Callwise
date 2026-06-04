"""Webhook-ingest API (PRD §3.1, §11.2).

A separate deployment from the control-plane API, scaled independently. It does almost
nothing synchronously — verify HMAC, dedup, write a raw event row, enqueue, return 200 —
so unpredictable provider bursts never compete with heavy report queries and always ACK
in <200ms. No JWT here; auth is HMAC + IP allowlist at the edge.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from callwise.config import get_settings
from callwise.logging import configure_logging, get_logger
from callwise.observability.tracing import setup_tracing
from callwise.queue.factory import get_queue
from callwise.webhook_ingest.routers import context, elevenlabs, exotel, twilio

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.app_env != "dev")
    # Ensure the verification consumer group exists so the first webhook can enqueue.
    queue = get_queue()
    await queue.ensure_group(settings.verify_stream, settings.verify_consumer_group)
    log.info("webhook_ingest_starting", env=settings.app_env)
    yield
    log.info("webhook_ingest_stopping")


def create_app() -> FastAPI:
    app = FastAPI(title="Callwise Webhook Ingest", version="0.1.0", lifespan=lifespan)
    setup_tracing(app, service_name="webhook-ingest")

    app.include_router(elevenlabs.router, prefix="/api/v2", tags=["elevenlabs"])
    app.include_router(exotel.router, prefix="/api/v2", tags=["exotel"])
    app.include_router(twilio.router, prefix="/api/v2", tags=["twilio"])
    app.include_router(context.router, prefix="/api/v2", tags=["context"])

    app.mount("/metrics", make_asgi_app())

    @app.get("/api/v2/health", tags=["health"])
    @app.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
