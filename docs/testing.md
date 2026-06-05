# Testing Callwise — full application guide

How to verify the **entire** Callwise stack: automated tests (unit + integration + lint),
frontend build, Docker compose smoke, and the manual end-to-end mock call path.

The default stack uses **mock providers** — no Exotel, Twilio, or OpenAI credentials required.

---

## What you are testing

| Layer | What it proves | Time |
|-------|----------------|------|
| **A · Backend automated** | Governors, idempotency SQL, HMAC, phone normalization, verification logic | ~2 min |
| **B · Integration / idempotency** | PRD §16.1 “run twice == run once” against real Postgres + Redis | ~1 min |
| **C · Frontend** | Next.js dashboard compiles and ships | ~2 min |
| **D · Docker full stack** | All services boot, migrate, seed, workers consume queues | ~5 min first build |
| **E · Manual E2E (mock call)** | Dashboard → outbound → dialer → webhook → verify → live card | ~30 s |

Layers **A–D** mirror CI (`.github/workflows/ci.yml`). Layer **E** is the product demo path from PRD §0.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| **Docker Desktop** | recent | For full stack + Postgres/Redis for local integration tests |
| **uv** | any recent | [install](https://docs.astral.sh/uv/getting-started/installation/) — Python 3.12 managed by uv |
| **Node.js** | 22.x | Frontend build only |
| **Git** | — | Clone the repo |

**Windows notes**

- After installing `uv`, restart the terminal so `uv` is on `PATH` (or use `%USERPROFILE%\.local\bin\uv.exe`).
- If `backend/.venv` was created on Linux/WSL (`bin/` not `Scripts/`), delete it and recreate on Windows:

  ```powershell
  Remove-Item -Recurse -Force backend\.venv
  cd backend
  uv sync --dev
  ```

- The full pytest suite **requires Redis** on `localhost:6379`. Without it, ~18 governor/state tests block on TCP timeout. Start Redis via Docker (see below) before running tests.

---

## One-shot checklist (copy/paste)

Run from the repo root (`D:\Callwise` or `./callwise`).

### 1. Infrastructure only (Postgres + Redis)

```bash
docker compose up -d postgres redis
```

Wait until healthy:

```bash
docker compose ps
```

### 2. Backend — install, migrate, test everything

**Linux / macOS / Git Bash**

```bash
cd backend
uv python install 3.12
uv sync --dev
export DATABASE_URL_DIRECT=postgresql+asyncpg://callwise:callwise@localhost:5432/callwise
export DATABASE_URL=postgresql+asyncpg://callwise:callwise@localhost:5432/callwise
export REDIS_URL=redis://localhost:6379/0
export CALLWISE_TEST_REDIS_URL=redis://localhost:6379/15
export CALLWISE_IT_DB=1
export JWT_SECRET=dev-only-change-me-to-a-32+char-random-secret
export CONTEXT_TOKEN_SECRET=dev-only-change-me-context-signing-secret
uv run alembic upgrade head
uv run ruff check .
uv run mypy src
uv run pytest -v
```

**Windows PowerShell**

```powershell
cd backend
uv python install 3.12
uv sync --dev
$env:DATABASE_URL_DIRECT = "postgresql+asyncpg://callwise:callwise@localhost:5432/callwise"
$env:DATABASE_URL        = "postgresql+asyncpg://callwise:callwise@localhost:5432/callwise"
$env:REDIS_URL           = "redis://localhost:6379/0"
$env:CALLWISE_TEST_REDIS_URL = "redis://localhost:6379/15"
$env:CALLWISE_IT_DB      = "1"
$env:JWT_SECRET          = "dev-only-change-me-to-a-32+char-random-secret"
$env:CONTEXT_TOKEN_SECRET = "dev-only-change-me-context-signing-secret"
uv run alembic upgrade head
uv run ruff check .
uv run mypy src
uv run pytest -v
```

**Expected:** all tests pass; **0 failures**. Integration tests are skipped when `CALLWISE_IT_DB` is unset.

Approximate counts (current tree):

- **~63 unit tests** — backoff, circuit breaker, compliance, governors, phone, retry, security, verification, webhooks, token efficiency
- **7 integration tests** — claim, dedup, upsert, forward-only CAS, outbox, redlock

### 3. Frontend

```bash
cd frontend
npm install
npm run build
npm run lint    # optional
```

### 4. Full Docker stack + manual E2E

```bash
# from repo root
docker compose up --build
```

When all services are up, follow [Manual E2E walkthrough](#manual-e2e-walkthrough-mock-outbound-call) below.

---

## Layer A — Backend automated tests (detail)

### Unit only (no Postgres)

Useful for quick iteration. Still needs **Redis** for governor tests.

```bash
cd backend
uv sync --dev
export CALLWISE_TEST_REDIS_URL=redis://localhost:6379/15   # or PowerShell $env:...
uv run pytest tests/unit -v
```

### Integration / idempotency suite only (PRD §16.1)

Requires Postgres (migrated) + `CALLWISE_IT_DB=1`:

```bash
cd backend
uv run alembic upgrade head    # uses DATABASE_URL_DIRECT
uv run pytest tests/integration -v
```

Tests live in `backend/tests/integration/test_idempotency.py`:

| Test | PRD section |
|------|-------------|
| `test_claim_contact_second_claim_returns_none` | §6.1 no double-dial |
| `test_claim_respects_max_attempts` | §6.1 attempt cap |
| `test_register_event_dedup` | §6.3 webhook dedup |
| `test_verification_upsert_overwrites_not_duplicates` | §6.3 upsert |
| `test_forward_only_status_absorbs_terminal` | §6.3 forward-only CAS |
| `test_outbox_dedup_key_exactly_once` | §9.5 outbox |
| `test_redlock_is_exclusive` | §6.4 campaign-start guard |

### Lint and type-check (matches CI `backend` job)

```bash
cd backend
uv run ruff check .
uv run mypy src
```

---

## Layer B — Run exactly what CI runs

CI splits into three jobs you can reproduce locally:

| CI job | Local equivalent |
|--------|------------------|
| `backend` | `uv run ruff check . && uv run mypy src && uv run pytest -q` (with Redis + env above) |
| `integration` | Same env as CI + `uv run pytest tests/integration -q` |
| `frontend` | `cd frontend && npm install && npm run build` |
| `docker` | `docker build -t callwise/backend:local backend` (on push only in CI) |

To mirror CI’s split integration job, run unit and integration separately:

```bash
cd backend
uv run pytest tests/unit -q
uv run pytest tests/integration -q    # needs CALLWISE_IT_DB + migrated DB
```

---

## Layer C — Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000 — hot reload
npm run build        # production build (CI gate)
npm run lint         # ESLint
```

The dashboard falls back to `frontend/mocks/seed.ts` when the API is unreachable. With the full stack running, it uses the real API and auto-logs in as the demo user.

---

## Layer D — Docker full stack smoke

### Start everything

```bash
docker compose up --build
```

No `.env` file is required — dev defaults are inlined in `docker-compose.yml`.

### Service URLs

| Service | URL |
|---------|-----|
| Landing page | http://localhost:3000 |
| Dashboard | http://localhost:3000/dashboard |
| Control API (OpenAPI) | http://localhost:8000/docs |
| Webhook ingest (OpenAPI) | http://localhost:8001/docs |
| Control API health | http://localhost:8000/api/health |
| Webhook health | http://localhost:8001/api/v2/health |
| Prometheus metrics | http://localhost:8000/metrics · http://localhost:8001/metrics |
| MinIO console | http://localhost:9001 (callwise / callwise123) |

### Smoke checks (curl)

```bash
# Health
curl -s http://localhost:8000/api/health
curl -s http://localhost:8001/api/v2/health

# Login (seeded demo user)
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@callwise.local","password":"demo12345"}'

# Reports feed (replace TOKEN)
curl -s http://localhost:8000/api/reports/feed \
  -H "Authorization: Bearer TOKEN"
```

### Worker logs (watch the mock call path)

```bash
docker compose logs -f dialer-worker verification-worker
```

You should see: claim → dial → mock webhook ACK → verification → outbox/WS event.

### Reset database and re-seed

```bash
docker compose down -v          # destroys volumes
docker compose up --build       # migrate + seed run again
```

---

## Manual E2E walkthrough (mock outbound call)

This is the **primary product test** — same path documented in the root `README.md`.

### Steps

1. `docker compose up --build` and wait until `seed` has completed and `control-api` is listening.
2. Open **http://localhost:3000/dashboard**.
3. Confirm the feed shows seeded query cards (dental clinic demo data).
4. Click **Start Outbound Call**.
5. Enter a valid Indian mobile, e.g. `+91 98765 43210`, and a name (optional).
6. Click trigger — status should show success.
7. Within **~5–15 seconds**, a **new query card** appears at the top of the feed (WebSocket push).
8. Click the card — detail panel shows summary, outcome tag, and transcript.

### What happens under the hood

```
Dashboard POST /api/call_sessions/outbound
  → contact queued + message on dial:stream
  → dialer-worker: claim → write-ahead session → governors → mock telephony
  → mock provider fires webhook → webhook-ingest → verify:stream
  → verification-worker: LLM (mock) → upsert verification → WS push
  → dashboard feed updates
```

### Demo credentials

| Field | Value |
|-------|-------|
| Email | `demo@callwise.local` |
| Password | `demo12345` |

Created by `callwise.scripts.seed_demo` (runs automatically in compose `seed` service).

### API-only E2E (no browser)

```bash
# 1. Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@callwise.local","password":"demo12345"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Trigger outbound
curl -s -X POST http://localhost:8000/api/call_sessions/outbound \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone":"+919876543210","customer_name":"API Test"}'

# 3. Poll feed until a new card appears (or watch WS)
curl -s http://localhost:8000/api/reports/feed -H "Authorization: Bearer $TOKEN"
```

---

## Local dev without Docker (advanced)

Run infra in Docker, apps on the host:

```bash
docker compose up -d postgres pgbouncer redis minio
```

Create `backend/.env` or export (hostnames must be `localhost`, not Docker service names):

```bash
export DATABASE_URL=postgresql+asyncpg://callwise:callwise@localhost:6432/callwise
export DATABASE_URL_DIRECT=postgresql+asyncpg://callwise:callwise@localhost:5432/callwise
export REDIS_URL=redis://localhost:6379/0
export BASE_URL=http://localhost:8001
export JWT_SECRET=dev-only-change-me-to-a-32+char-random-secret
export CONTEXT_TOKEN_SECRET=dev-only-change-me-context-signing-secret
export TELEPHONY_PROVIDER=mock
export CONVERSATION_PROVIDER=mock
export LLM_PROVIDER=mock
```

Then in separate terminals:

```bash
cd backend && uv run alembic upgrade head && uv run python -m callwise.scripts.seed_demo
cd backend && uv run uvicorn callwise.control_api.main:app --reload --port 8000
cd backend && uv run uvicorn callwise.webhook_ingest.main:app --reload --port 8001
cd backend && uv run python -m callwise.workers.dialer
cd backend && uv run python -m callwise.workers.verification
cd backend && uv run python -m callwise.workers.reconciler
cd frontend && npm run dev
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `uv: command not found` | Install uv; restart terminal; or use full path to `uv.exe` |
| `pytest` hangs on governor tests | Start Redis: `docker compose up -d redis` |
| `ZoneInfoNotFoundError: Asia/Kolkata` | Run `uv sync --dev` (installs `tzdata` from lockfile) |
| `uv run` fails dependency resolution | Use `uv sync --dev --frozen` (respects `uv.lock`) |
| Integration tests all skipped | Set `CALLWISE_IT_DB=1` and `DATABASE_URL_DIRECT` |
| Alembic connection refused | Postgres not up, or wrong host (`localhost` vs `postgres`) |
| Dashboard empty, no auto-login | Run `seed` service or `uv run python -m callwise.scripts.seed_demo` |
| Outbound queued but no card | Check `dialer-worker` and `verification-worker` logs; Redis/Postgres healthy |
| Frontend can’t reach API | `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` (compose sets this) |
| Old Linux `.venv` on Windows | Delete `.venv`, run `uv sync --dev` |

---

## What is NOT covered yet

These PRD §16 items have **no automated harness** in the repo today:

- **Contract tests** — recorded Exotel/Twilio/ElevenLabs fixtures
- **Load test** — ramp to 3k initiations/min with failure injection
- **Soak test** — hours-long stability
- **Chaos test** — kill worker mid-dial, Redis restart, Postgres failover

The mock telephony provider (`providers/telephony/mock.py`) is designed to be tunable for future load tests, but no runner script exists yet.

---

## Quick pass/fail summary

You can sign off a full local verification when:

- [ ] `uv run ruff check .` — clean
- [ ] `uv run mypy src` — clean
- [ ] `uv run pytest` — **all passed**, 0 failed (integration not skipped)
- [ ] `npm run build` in `frontend/` — succeeds
- [ ] `docker compose up --build` — all services healthy
- [ ] Manual outbound call — **new query card** in dashboard within ~15 s
- [ ] `curl` health endpoints return OK

---

## Related docs

- [Architecture](architecture.md) — system overview and rollout phases
- [Idempotency](idempotency.md) — master idempotency design (PRD §6)
- [Vendors](vendors.md) — provider matrix and switching real providers for staging tests
- [Runbooks](runbooks/README.md) — operational procedures (partial)
