"""Control-plane API (PRD §3.1, §11.1).

Authenticated (JWT), row-level ownership, campaigns/contacts/reports. Deployed and scaled
independently from the webhook-ingest API so a heavy report query can never starve webhook
ingestion. Reports are served from a read replica in production (PRD §4.3).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from callwise.config import get_settings
from callwise.control_api.routers import (
    auth,
    call_sessions,
    campaigns,
    contacts,
    jobs,
    recordings,
    reports,
    ws,
)
from callwise.logging import configure_logging, get_logger
from callwise.observability.tracing import setup_tracing
from callwise.storage import get_object_store

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.app_env != "dev")
    try:
        await get_object_store().ensure_bucket()
    except Exception:  # noqa: BLE001 — storage is best-effort; never block startup
        log.warning("object_store_init_skipped")
    log.info("control_api_starting", env=settings.app_env)
    yield
    log.info("control_api_stopping")


def create_app() -> FastAPI:
    app = FastAPI(title="Callwise Control API", version="0.1.0", lifespan=lifespan)
    setup_tracing(app, service_name="control-api")

    # CORS: the dashboard runs in the browser at a different origin than this API, so every
    # request is preceded by an OPTIONS preflight. Without this middleware the preflight 405s
    # and the browser blocks the call ("backend not connected"). Bearer-token auth (no cookies)
    # lets us safely allow "*" in dev; prod narrows it via CORS_ALLOW_ORIGINS.
    origins = get_settings().cors_origins_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(campaigns.router, prefix="/api/campaigns", tags=["campaigns"])
    app.include_router(contacts.router, prefix="/api/contacts", tags=["contacts"])
    app.include_router(call_sessions.router, prefix="/api/call_sessions", tags=["calls"])
    app.include_router(recordings.router, prefix="/api/recordings", tags=["recordings"])
    app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(ws.router, prefix="/api", tags=["ws"])

    app.mount("/metrics", make_asgi_app())

    @app.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
