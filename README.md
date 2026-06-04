# Callwise

> An AI voice agent that answers inbound calls, makes outbound follow-ups, and turns
> every conversation into a clean, tagged query in one dashboard.

Callwise has **two faces over one machine**:

- **The shop window (Part A)** — a demoable portfolio product a non-technical client
  immediately gets: inbound/outbound AI voice agent → a live dashboard where every call
  becomes a searchable, outcome-tagged *query card*.
- **The delivery engine (Part B)** — the production system beneath it, engineered for
  thousands of concurrent calls per minute with strict idempotency, per-session context
  isolation, distributed governors, and full fault tolerance.

The full specification lives in `PRD_Callwise_Production.md` (untracked — it's the private
spec shared only after a client is interested).

---

## Repository layout

```
callwise/
├── backend/        # Python 3.12 · FastAPI · async SQLAlchemy · Redis Streams
│   ├── src/callwise/
│   │   ├── control_api/      # control-plane API (auth, campaigns, contacts, reports)
│   │   ├── webhook_ingest/   # webhook-ingest API (HMAC verify, dedup, fast ACK)
│   │   ├── workers/          # dialer · verification · reconciler (sharded by concern)
│   │   ├── governors/        # token bucket · concurrency semaphore · circuit breaker
│   │   ├── providers/        # pluggable telephony / conversation / LLM behind factories
│   │   ├── domain/           # idempotency, context snapshots, conversation state, phone
│   │   ├── queue/            # broker abstraction (Redis Streams default, SQS path)
│   │   ├── reliability/      # backoff, retry classification, transactional outbox
│   │   ├── db/               # models, enums, async engine (PgBouncer-safe)
│   │   └── observability/    # Prometheus metrics, OpenTelemetry tracing
│   ├── alembic/              # migrations
│   └── tests/                # unit · integration · idempotency suite
├── frontend/       # Next.js (App Router) · TypeScript · Tailwind — landing + dashboard
├── infra/          # Kubernetes manifests, KEDA, PgBouncer, Redis config
├── docs/           # architecture, data model, idempotency, runbooks
└── docker-compose.yml   # full local stack (postgres, pgbouncer, redis, minio, apps)
```

See [`docs/architecture.md`](docs/architecture.md) for the system overview and
[`docs/idempotency.md`](docs/idempotency.md) for the master idempotency design.

---

## Quickstart (local dev)

### Everything at once (Docker)

```bash
cp .env.example .env          # optional: dev defaults are baked into compose
docker compose up --build
```

| Service        | URL                             |
|----------------|---------------------------------|
| Dashboard      | http://localhost:3000/dashboard |
| Landing page   | http://localhost:3000           |
| Control API    | http://localhost:8000/docs      |
| Webhook ingest | http://localhost:8001/docs      |
| MinIO console  | http://localhost:9001           |

The default provider stack is **mock** (`TELEPHONY_PROVIDER=mock`, etc.), so the stack
boots and runs simulated calls with no external credentials — matching the load-test
harness in PRD §16.

### Backend only

```bash
cd backend
uv sync                       # install pinned deps (uv.lock is the single source of truth)
uv run alembic upgrade head   # apply migrations (point DATABASE_URL_DIRECT at Postgres)
uv run uvicorn callwise.control_api.main:app --reload --port 8000
uv run uvicorn callwise.webhook_ingest.main:app --reload --port 8001
uv run python -m callwise.workers.dialer
```

### Frontend only

```bash
cd frontend
npm install
npm run dev                   # http://localhost:3000
```

The dashboard ships with seeded example query cards (`frontend/mocks/seed.ts`), so the
feed looks alive on first load even without the backend running.

---

## The core principle

> **Initiations are elastic; live calls are sacred.** Under stress, the system stops
> *starting* new calls (sheds load at the queue) but never drops a call already in
> progress and never loses its record.

---

## Status

🚧 **Scaffold.** Directory structure, configuration, the data model, the reliability
primitives (governors, idempotency, outbox, backoff), provider interfaces, both API
apps, the worker loops, and the demo frontend are in place. Endpoint bodies and provider
integrations are marked with `TODO` and wired to working interfaces. See the
[rollout plan](docs/architecture.md) for phasing.
