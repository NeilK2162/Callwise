"""Prometheus metrics (PRD §13.1).

The named series the dashboards and alerts in §13.2/§13.3 are built on. Import these
counters/gauges/histograms where the events happen; expose `/metrics` from each app.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# --- Dialer ---
DIALS_INITIATED = Counter("dials_initiated_total", "Dials initiated", ["campaign"])
DIALS_FAILED = Counter("dials_failed_total", "Dials failed", ["reason"])
CALLS_LIVE = Gauge("calls_live", "Concurrent live calls", ["scope"])
CALL_DURATION = Histogram("call_duration_seconds", "Call duration (s)")

# --- Webhooks ---
WEBHOOK_RECEIVED = Counter("webhook_received_total", "Webhooks received", ["provider", "type"])
WEBHOOK_DEDUP_HITS = Counter("webhook_dedup_hits_total", "Duplicate webhooks ignored")

# --- Queue / workers ---
QUEUE_LAG = Gauge("queue_lag", "Pending entries", ["stream"])
TASK_DURATION = Histogram("task_duration_seconds", "Task duration (s)", ["task"])
DLQ_DEPTH = Gauge("dlq_depth", "Dead-letter queue depth", ["stream"])

# --- Governors ---
RATE_LIMITER_DENIED = Counter("rate_limiter_denied_total", "Rate-limit denials", ["provider"])
CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state", "0=closed 1=half_open 2=open", ["provider"]
)
CONCURRENCY_SLOTS_USED = Gauge("concurrency_slots_used", "Live slots in use", ["scope"])

# --- Verification / cost ---
VERIFICATION_CONFIDENCE = Histogram("verification_confidence", "LLM verification confidence")
LLM_TOKENS_USED = Counter("llm_tokens_used_total", "LLM tokens consumed")
COST_MICROS = Counter("cost_micros_total", "Call cost (micros)", ["campaign"])

# --- Infra ---
DB_POOL_IN_USE = Gauge("db_pool_in_use", "DB connections checked out")
