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
    from callwise.config import get_settings

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    endpoint = get_settings().otel_exporter_otlp_endpoint
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
            )
        except Exception:  # noqa: BLE001 — exporter is optional; tracing must never block boot
            pass
    trace.set_tracer_provider(provider)
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        except Exception:  # noqa: BLE001 — tracing is best-effort, never blocks startup
            pass


def get_tracer(name: str = "callwise") -> trace.Tracer:
    return trace.get_tracer(name)
