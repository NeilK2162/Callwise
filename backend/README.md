# Callwise — Backend

Python 3.12 · FastAPI · async SQLAlchemy (asyncpg) · Redis Streams · Alembic.

Two API deployments and three worker fleets share one package (`src/callwise`):

| Entrypoint | Module | Role |
|---|---|---|
| Control API | `callwise.control_api.main:app` | Auth, campaigns, contacts, reports (JWT, row-level ownership) |
| Webhook ingest | `callwise.webhook_ingest.main:app` | HMAC verify → dedup → persist → enqueue → fast ACK |
| Dialer worker | `python -m callwise.workers.dialer` | Claim contact → governed dispatch → provider dial |
| Verification worker | `python -m callwise.workers.verification` | Post-call LLM pipeline (transcript, verify, summarize) |
| Reconciler | `python -m callwise.workers.reconciler` | Stale-session sweep, orphan recovery, outbox dispatch |

## Layout

```
src/callwise/
  config.py            # pydantic-settings; startup validation (JWT >= 32 chars)
  logging.py           # structured JSON logs with correlation ids
  db/                  # async engine (PgBouncer-safe), models, enums
  domain/              # idempotency SQL, context snapshots, conversation state, phone
  governors/           # token bucket · concurrency semaphore · circuit breaker
  reliability/         # backoff, retry classification, transactional outbox
  queue/               # broker abstraction — Redis Streams default, SQS migration path
  providers/           # telephony / conversation / llm behind factories (+ mock impls)
  control_api/         # control-plane FastAPI app
  webhook_ingest/      # webhook-ingest FastAPI app
  workers/             # dialer · verification · reconciler loops
  observability/       # Prometheus metrics, OpenTelemetry tracing
```

## Dev

```bash
uv sync                         # install pinned deps
uv run alembic upgrade head     # migrate (uses DATABASE_URL_DIRECT)
uv run uvicorn callwise.control_api.main:app --reload --port 8000
uv run pytest                   # tests (incl. the mandatory idempotency suite)
uv run ruff check . && uv run mypy src
```

Full-stack testing guide (unit + integration + Docker + manual E2E):
[`../docs/testing.md`](../docs/testing.md).

> Behind PgBouncer transaction pooling the async engine sets `statement_cache_size=0`
> (PRD §9.7) — prepared-statement caching corrupts otherwise. This is handled in
> `db/base.py`; don't remove it.

Provider matrix and doc links: [`../docs/vendors.md`](../docs/vendors.md).
