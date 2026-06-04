"""OpenTelemetry tracing setup (PRD §13.1).

A distributed trace per call spans claim → dial → provider → webhook → verification, so
the slow span is findable instantly. Call `setup_tracing(app)` from each FastAPI app;
exporter wiring (OTLP endpoint) is environment-driven and left to deployment config.
"""

from __future__ import annotations

from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider


def setup_tracing(app: Any | None = None, *, service_name: str = "callwise") -> None:
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    trace.set_tracer_provider(provider)
    # TODO: add an OTLPSpanExporter + BatchSpanProcessor from OTEL_EXPORTER_OTLP_ENDPOINT.
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        except Exception:  # noqa: BLE001 — tracing is best-effort, never blocks startup
            pass


def get_tracer(name: str = "callwise") -> trace.Tracer:
    return trace.get_tracer(name)
