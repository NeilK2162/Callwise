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
├── docs/           # architecture, data model, idempotency, vendors, runbooks
└── docker-compose.yml   # full local stack (postgres, pgbouncer, redis, minio, apps)
```

See [`docs/architecture.md`](docs/architecture.md) for the system overview,
[`docs/idempotency.md`](docs/idempotency.md) for the master idempotency design, and
[`docs/vendors.md`](docs/vendors.md) for all external vendors and documentation links.

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
>
> **Spend tokens only where they change the outcome.** One LLM call per answered call —
> classification + extraction + summary together, on a trimmed transcript, behind a
> per-minute token budget and a per-campaign spend ceiling (PRD §19; summarized in
> [`docs/architecture.md`](docs/architecture.md)).

---

## Status

**Working end-to-end (mock stack, no external creds).** Trigger a call from the dashboard
and watch a tagged query card slide into the feed in real time:

`docker compose up --build` → [dashboard](http://localhost:3000/dashboard) → **Start
Outbound Call** → contact is created → dialer claims + governed-dispatches → the mock
provider simulates the PSTN lifecycle → webhook → verification (one LLM call) → live WS
push → card appears. Seeded demo data + auto-login mean the feed is alive on first load.

**Providers implemented against official docs/MCP connectors:**

| Layer | Real | Stub |
|---|---|---|
| Telephony | mock · **Exotel** · **Twilio** (calls.create + AMD + real `X-Twilio-Signature`) | Plivo, Telnyx |
| Conversation | mock · **ElevenLabs** (webhook + `t,v0` HMAC) · **LiveKit + Soniox** (agent runtime) | — |
| LLM | mock · **OpenAI / Azure** (Structured Outputs + caching + escalation) | Anthropic |

See [`docs/vendors.md`](docs/vendors.md) for the full vendor → status → connector matrix.

**Cost & efficiency** (PRD §19): single-call verify+summary, prompt caching, output
caps, transcript trimming, no-LLM short-circuits, cheap-model-with-escalation, a TPM
token-budget limiter, and per-campaign spend-ceiling auto-pause.

**Compliance:** calling-window (TCPA/TRAI), cross-campaign DND suppression, opt-out.

**Validated:** `ruff` clean · unit suite green (incl. governor/redlock/state tests against
real Redis) · frontend `next build` passes · the **idempotency suite runs in CI** against
Postgres + Redis service containers (`.github/workflows/ci.yml`).

**Still stubbed:** Anthropic adapter, S3 presigned URLs, Plivo/Telnyx, Grafana dashboards.
See the [rollout plan](docs/architecture.md) for phasing.
