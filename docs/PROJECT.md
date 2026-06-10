# Callwise — Project Document

**Version:** 1.0 · June 2026  
**Sources:** `PRD_Callwise_Production.md` (full engineering spec) + repository audit  
**Audience:** Product, engineering, sales, and technical stakeholders who need the whole truth — what exists today and what is planned.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Two Faces of Callwise](#2-the-two-faces-of-callwise)
3. [Product Features — Current vs Planned](#3-product-features--current-vs-planned)
4. [System Architecture](#4-system-architecture)
5. [Data Model](#5-data-model)
6. [API Surface](#6-api-surface)
7. [Frontend & User Experience](#7-frontend--user-experience)
8. [Provider Integrations](#8-provider-integrations)
9. [Reliability, Idempotency & Governors](#9-reliability-idempotency--governors)
10. [Compliance & Security](#10-compliance--security)
11. [Cost & Token Efficiency](#11-cost--token-efficiency)
12. [Observability & Operations](#12-observability--operations)
13. [Infrastructure & Deployment](#13-infrastructure--deployment)
14. [Testing & Quality](#14-testing--quality)
15. [Rollout Plan](#15-rollout-plan)
16. [Known Gaps & TODOs](#16-known-gaps--todos)
17. [Scale Targets & SLOs (Planned Production)](#17-scale-targets--slos-planned-production)
18. [Related Documents](#18-related-documents)

---

## 1. Executive Summary

**Callwise** is a vertical-neutral AI voice-agent platform. It answers inbound calls, makes outbound follow-ups, and turns every conversation into a **tagged, searchable query card** in a single dashboard.

### One-line pitch

> Callwise answers your inbound calls and makes your outbound follow-ups with a natural AI voice — and every conversation shows up in one dashboard as a clean, searchable query with the outcome already tagged.

### Core principles

1. **Initiations are elastic; live calls are sacred.** Under stress, the system stops *starting* new calls but never drops a live call or loses its record.
2. **Exactly-once business effects.** No double-dials, no duplicate verifications, no duplicate webhook effects.
3. **Per-session isolation.** Every concurrent call carries its own immutable context and mutable state — zero cross-talk.
4. **Spend tokens only where they change the outcome.** One LLM call per answered call; skip the model when the answer is free.

### Current state (honest snapshot)

| Dimension | Status |
|-----------|--------|
| **End-to-end product demo** | ✅ Working on mock stack (Docker Compose) |
| **Production scale (3k–10k calls/min)** | 📋 Specified in PRD; not load-validated yet |
| **Real provider stack** | ✅ Adapters implemented (Exotel, Twilio, ElevenLabs, LiveKit, OpenAI/Azure); requires credentials |
| **Portfolio demo (live inbound number)** | ⚠️ Landing page has placeholder number; needs real PSTN wiring |
| **CI / idempotency suite** | ✅ Green in GitHub Actions |
| **Observability dashboards** | 📋 Metrics exposed; Grafana/Loki not built |

---

## 2. The Two Faces of Callwise

Callwise is deliberately **one machine with two faces**:

| | Portfolio / Shop Window (Part A) | Production / Delivery Engine (Part B) |
|---|---|---|
| **Audience** | Non-technical clients, Upwork buyers | Engineers, technical reviewers |
| **Goal** | "I want that" in 30 seconds | "This won't fall over at scale" |
| **Shows** | Inbound/outbound + dashboard + live call | Idempotency, governors, edge cases, SLOs |
| **Code** | `frontend/` | `backend/`, `infra/` |
| **Visibility** | Public — landing page, demo video | Private — shared after interest |

### The query card (centerpiece artifact)

Every call — inbound or outbound — produces one card:

- Caller identity (masked phone)
- Direction (inbound/outbound) and timestamp
- One-line AI summary
- Outcome tag (plain English)
- Extracted fields (name, service, date, etc.)
- Actions: play recording, view transcript, export

**Outcome tags** (vertical-configurable, stored as enums):

`appointment_booked` · `question_answered` · `callback_needed` · `not_interested` · `wrong_number` · `wrong_party` · `voicemail` · `opt_out` · `undetermined`

### Demo scope (what converts)

| Must-have | Status |
|-----------|--------|
| Live "call this number" on landing page | ⚠️ UI exists; `+1 (555) 010-2024` is placeholder |
| Working dashboard (feed + card detail) | ✅ Built |
| "Trigger outbound call" button | ✅ Built |
| One vertical skin (dental clinic) | ✅ Seeded demo data |
| 2–3 pre-seeded example calls | ✅ `seed_demo` + `frontend/mocks/seed.ts` fallback |

**Deliberately excluded from demo** (per PRD §0.7): auth/login screen, multi-tenant UI, billing, settings sprawl.

---

## 3. Product Features — Current vs Planned

### 3.1 Inbound calling — "never miss a call"

| Feature | Current | Planned |
|---------|---------|---------|
| Answer inbound PSTN calls 24/7 | Adapter code exists (Exotel, Twilio) | Wire real number to landing page |
| Natural multi-turn conversation | ElevenLabs ConvAI + LiveKit agent paths | Production tuning per vertical |
| After-hours coverage | Architecture supports it | Client-specific deployment |
| Capture details + flag callback | ✅ Verification pipeline tags outcomes | — |
| Warm transfer to human | `allowed_actions` in context snapshot | Full SIP bridge implementation |

### 3.2 Outbound calling — "follow up automatically"

| Feature | Current | Planned |
|---------|---------|---------|
| Campaign-based outbound dialing | ✅ Campaign lifecycle + dialer worker | — |
| Ad-hoc single outbound (dashboard button) | ✅ `POST /api/call_sessions/outbound` | — |
| Contact list upload (CSV) | ✅ Sync path ≤8 MiB | Async worker for large files (>50k rows) |
| Appointment reminders, lead qual, feedback | Agent prompt/config driven | Vertical-specific agent templates |
| AMD (answering machine detection) | ✅ Twilio adapter supports AMD flag | Exotel AMD tuning |
| Calling-window enforcement (TCPA/TRAI) | ✅ `compliance.py` (skipped for mock) | Per-jurisdiction campaign config |
| DND / do-not-contact suppression | ✅ `domain/suppression.py` | External DND registry API integration |
| Opt-out during call | ✅ `opt_out` outcome + `do_not_contact` status | Agent FSM action wiring |

### 3.3 Dashboard — "everything in one place"

| Feature | Current | Planned |
|---------|---------|---------|
| Stats bar (calls, booked, callback, missed, avg duration) | ✅ `StatsBar` + `/api/reports/summary` | Inbound-specific missed-call metric |
| Query feed (newest first) | ✅ `/api/reports/feed` | Pagination / infinite scroll |
| Filters: All / Inbound / Outbound / Needs Action | ✅ Client-side + API `needs_action` | Server-side direction filter |
| Search | ✅ `q` param on feed | Full-text search index |
| Card detail slide-out (transcript, recording, extracted) | ✅ `CardDetail` component | Recording playback (needs S3 presign) |
| Real-time feed updates | ✅ WebSocket `/api/ws` | Live transcript stream (LiveKit path) |
| Export query card | UI placeholder | CSV/XLSX export (`/api/reports/export` TODO) |
| Offline/demo fallback | ✅ `frontend/mocks/seed.ts` | — |

### 3.4 Campaign management (operator-facing)

| Feature | Current | Planned |
|---------|---------|---------|
| Create / list / get / delete campaigns | ✅ | — |
| Start / pause / resume (idempotent start) | ✅ Redlock + `start_locked` | Scheduled start |
| Pacing config (concurrency, dials/min, attempts) | ✅ DB fields + dialer respects | UI for campaign config |
| Spend ceiling auto-pause | ✅ Accrual in verification worker | Spend dashboard |
| Bulk contact delete | Partial | Full CRUD per PRD §11.1 |

### 3.5 Post-call intelligence

| Feature | Current | Planned |
|---------|---------|---------|
| Transcript assembly | ✅ From provider webhooks | S3 archival |
| LLM verification (outcome + extraction + summary) | ✅ Single structured call | — |
| Provider summary reuse (ElevenLabs) | ✅ Short-circuit path | — |
| Cheap model + escalate on low confidence | ✅ `gpt-4o-mini` → strong model | Anthropic path |
| Manual re-verify | ⚠️ Endpoint logs; enqueue TODO | Wire to verify queue |
| Commission / outcome events | ✅ Transactional outbox | Real event bus consumers |

### 3.6 Platform & multi-tenancy

| Feature | Current | Planned |
|---------|---------|---------|
| JWT auth (login/register/logout) | ✅ | Token revocation denylist (Redis) |
| Row-level ownership | ✅ `owned_or_404` on all queries | Postgres RLS (defense-in-depth) |
| Superuser role | ✅ | Admin UI |
| Multi-tenant management UI | — | Not a demo goal |
| Billing screens | — | Not in scope |

---

## 4. System Architecture

### 4.1 High-level diagram

```
                         ┌──────────────────────────────┐
                         │   CDN / WAF / Rate-limit edge │  (production)
                         └───────────────┬──────────────┘
                                         │
            ┌────────────────────────────┼────────────────────────────┐
            │                            │                            │
   ┌────────▼────────┐          ┌────────▼────────┐          ┌────────▼────────┐
   │  control-api    │          │ webhook-ingest  │          │   frontend      │
   │  (FastAPI :8000)│          │ (FastAPI :8001) │          │ (Next.js :3000) │
   │  JWT, campaigns │          │ HMAC, dedup, ACK│          │ landing+dashboard│
   └────────┬────────┘          └────────┬────────┘          └─────────────────┘
            │                            │
            └──────────────┬─────────────┘
                           │
              ┌────────────▼────────────┐
              │   Redis Streams (broker) │
              │   dial:stream            │
              │   verify:stream          │
              │   dlq:stream             │
              └────────────┬────────────┘
                           │
     ┌─────────────────────┼─────────────────────┐
     │                     │                     │
┌────▼─────┐      ┌────────▼────────┐    ┌───────▼────────┐
│ dialer-  │      │ verification-   │    │ reconciler     │
│ worker   │      │ worker          │    │ sweep + outbox │
└────┬─────┘      └─────────────────┘    └────────────────┘
     │ governors: token bucket · concurrency · circuit breaker
     ▼
telephony (Exotel/Twilio/mock) → conversation (ElevenLabs/LiveKit/mock) → LLM (OpenAI/Azure/mock)

Postgres (via PgBouncer) · Redis (locks, governors, conv state) · MinIO/S3 (audio)
```

### 4.2 Critical architectural decisions

| Decision | Rationale | Status |
|----------|-----------|--------|
| Split control-api and webhook-ingest | Webhook bursts must ACK <200ms without competing with reports | ✅ Two deployments |
| Redis Streams + consumer groups (not Celery) | Durability, replay, PEL for at-least-once; SQS migration path | ✅ Implemented |
| Workers sharded by concern | LLM backlog must not slow dialing | ✅ dialer / verification / reconciler |
| PgBouncer transaction pooling | Thousands of tasks exhaust raw Postgres connections | ✅ In docker-compose + infra |
| Provider factory pattern | Swap telephony/conversation/LLM without code changes | ✅ `providers/*/factory.py` |

### 4.3 Two hot paths

**Dial path** (`workers/dialer.py`):

```
claim contact (atomic UPDATE) → create context snapshot → write-ahead call_session
→ acquire concurrency slot + rate-limit token → place call (idempotency key = session_id)
→ provider bridges to conversation layer
```

**Post-call path** (`webhook_ingest` → `workers/verification.py`):

```
verify HMAC → dedup (processed_events) → enqueue verify:stream
→ assemble transcript → LLM verify (one customer, one call) → upsert verification
→ tag contact → outbox event → WebSocket push to dashboard
```

**Reconciler** (`workers/reconciler.py`): sweeps stale sessions, recovers orphaned contacts, dispatches outbox. Runs every ~45s.

### 4.4 Repository layout

```
callwise/
├── backend/           # Python 3.12 · FastAPI · async SQLAlchemy · Redis Streams
│   ├── src/callwise/
│   │   ├── control_api/      # control-plane API
│   │   ├── webhook_ingest/   # webhook-ingest API
│   │   ├── workers/          # dialer · verification · reconciler
│   │   ├── governors/        # rate limiter · concurrency · circuit breaker · token budget
│   │   ├── providers/        # telephony · conversation · LLM
│   │   ├── domain/           # idempotency · snapshots · verification · phone · ingest
│   │   ├── queue/            # Redis Streams abstraction
│   │   ├── reliability/      # backoff · retry · outbox
│   │   ├── db/               # models · enums · async engine
│   │   └── observability/    # Prometheus metrics · OpenTelemetry (partial)
│   ├── alembic/              # migrations (0001_initial)
│   └── tests/                # ~63 unit + 7 integration
├── frontend/          # Next.js App Router · TypeScript · Tailwind
├── infra/             # K8s manifests · KEDA · PgBouncer · Redis config
├── docs/              # architecture · data-model · idempotency · vendors · testing · PROJECT
└── docker-compose.yml # full local stack
```

---

## 5. Data Model

Defined in `backend/src/callwise/db/models.py`, migrated by Alembic.

### Entity relationships

```
users ──< campaigns ──< contacts ──< call_sessions ──< call_events
                              │             │
                              │             ├──< transcripts (1:1)
                              │             ├──< recordings
                              │             └──< call_verifications (unique: session, step)
                              │
context_snapshots (1 per dial attempt, immutable)
processed_events  (webhook dedup)
outbox            (exactly-once event publishing)
ingest_jobs       (async CSV import progress)
```

### Key tables

| Table | Purpose | Notable columns |
|-------|---------|-----------------|
| `users` | Operators | `email`, `password_hash` (argon2), `is_superuser` |
| `campaigns` | Dial campaigns | `status`, pacing (`max_concurrent_calls`, `dials_per_minute`), `spend_ceiling_micros`, `meta.start_locked` |
| `contacts` | Dial unit | `phone_e164`, `status`, `attempt_count`, claim lease (`claimed_by`, `lease_expires_at`), `outcome_tags` |
| `context_snapshots` | Immutable per-attempt context | Frozen contact + agent config; never UPDATEd |
| `call_sessions` | One per dial attempt | `id` = provider idempotency key; forward-only `status` |
| `call_verifications` | Post-call LLM result | Unique `(call_session_id, step)` |
| `processed_events` | Webhook dedup | PK = `event_id` |
| `outbox` | Reliable domain events | Unique `dedup_key` |

### State machines

**Contact:** `queued → in_progress → {completed | no_answer | failed | dnd | do_not_contact}`; retries while `attempt_count < max_attempts`.

**Call session:** `dialing → ringing → in_progress → {completed | voicemail}` or early terminal (`no_answer`, `busy`, `failed`, `canceled`). Forward-only CAS.

**Campaign:** `draft → scheduled → running → paused → completed → archived`.

### Production-only (planned)

- Range partitioning on `call_events` and `processed_events` by month
- Read replica for reports
- Retention: transcripts 90d → Glacier; `processed_events` 30d; outbox 7d

---

## 6. API Surface

### 6.1 Control-plane API (`:8000`, JWT-authenticated)

| Method | Path | Status | Purpose |
|--------|------|--------|---------|
| POST | `/api/auth/login` · `/register` · `/logout` | ✅ | Auth |
| POST | `/api/contacts/upload` | ✅ sync; async TODO | CSV import → campaign |
| GET | `/api/contacts/template` | ✅ | CSV template |
| GET/POST/DELETE | `/api/campaigns/...` | ✅ | Campaign CRUD + lifecycle |
| GET | `/api/contacts/...` | ✅ partial | Contact list |
| GET | `/api/call_sessions/{id}` | ✅ | Session detail |
| GET | `/api/call_sessions/{id}/transcript` | ✅ | Transcript + summary |
| GET | `/api/call_sessions/{id}/verifications` | ✅ | Verification history |
| POST | `/api/call_sessions/{id}/analyze` | ⚠️ | Manual re-verify (enqueue TODO) |
| POST | `/api/call_sessions/outbound` | ✅ | Dashboard outbound trigger |
| GET | `/api/recordings/{id}/url` | ⚠️ | S3 presign TODO |
| GET | `/api/reports/summary` | ✅ | Stats bar data |
| GET | `/api/reports/feed` | ✅ | Query cards |
| GET | `/api/reports/export` | ⚠️ | CSV export TODO |
| GET | `/api/jobs/{id}` | ✅ | Ingest job status |
| WS | `/api/ws` | ✅ feed push | Live card updates |
| WS | `/api/ws/transcripts` | ⚠️ | Live transcript TODO |
| GET | `/api/health` | ✅ | Liveness |
| GET | `/metrics` | ✅ | Prometheus |

### 6.2 Webhook-ingest API (`:8001`, HMAC-verified)

| Method | Path | Status | Purpose |
|--------|------|--------|---------|
| POST | `/api/v2/webhooks/elevenlabs` | ✅ | Post-call transcription/audio/failure |
| POST | `/api/v2/webhooks/exotel/call-status` | ✅ | Exotel status callback |
| POST | `/api/v2/webhooks/twilio` | ✅ | Twilio status (signature validated) |
| POST | `/api/v2/webhooks/livekit` | ✅ | LiveKit events |
| POST | `/api/v2/webhooks/mock` | ✅ dev only | Mock provider lifecycle |
| GET | `/api/v2/exotel/call-context` | ✅ | Signed dynamic vars for ConvAI |
| GET | `/api/v2/exotel/connect-params` | ⚠️ | SIP connect params TODO |
| GET | `/api/v2/health` | ✅ | Liveness |
| GET | `/metrics` | ✅ | Prometheus |

---

## 7. Frontend & User Experience

**Stack:** Next.js (App Router) · TypeScript · Tailwind CSS · Lucide icons

### Pages

| Route | Purpose | Status |
|-------|---------|--------|
| `/` | Landing page — hero, ROI math, how-it-works, pricing, CTA | ✅ |
| `/dashboard` | Clinic dashboard — stats, filters, feed, outbound modal | ✅ |

### Components

| Component | Purpose |
|-----------|---------|
| `StatsBar` | Calls today, booked %, callbacks, missed (0 by design), avg duration |
| `Filters` | All / Inbound / Outbound / Needs Action + search |
| `QueryCard` | Feed card with direction, summary, outcome tag |
| `CardDetail` | Slide-out: transcript, extracted fields, recording link |
| `OutboundModal` | Phone + name → triggers outbound call |

### Auth UX

Per PRD §0.7, the dashboard has **no visible login screen**. It auto-logs in as `demo@callwise.dev` / `demo12345` via `frontend/lib/api.ts`. If the API is unreachable, it falls back to `frontend/mocks/seed.ts` (offline demo).

### Landing page gap

The "Call the agent now" button uses `+1 385 396 2012` (the live demo line). Wire this number to Twilio + ElevenLabs ConvAI for the portfolio demo.

---

## 8. Provider Integrations

Three pluggable seams behind factories. Switch via environment variables.

```bash
TELEPHONY_PROVIDER=mock      # mock | exotel | twilio | plivo | telnyx
CONVERSATION_PROVIDER=mock   # mock | elevenlabs | livekit
LLM_PROVIDER=mock            # mock | azure_openai | openai | anthropic
```

### Status matrix

| Layer | Live (code exists) | Stub / Planned |
|-------|-------------------|----------------|
| **Telephony** | mock, Exotel, Twilio (AMD, signature validation) | Plivo, Telnyx |
| **Conversation** | mock, ElevenLabs (webhook + HMAC), LiveKit + Soniox agent | — |
| **LLM** | mock, OpenAI, Azure OpenAI (Structured Outputs, caching, escalation) | Anthropic |
| **Object storage** | MinIO (local) | S3 presigned URLs |
| **Queue** | Redis Streams | SQS (migration path) |

### Conversation paths

1. **ElevenLabs ConvAI (SIP, default for scale):** Provider bridges PSTN ↔ ConvAI. Dynamic context via signed `call-context` endpoint. Lower operational burden.
2. **LiveKit real-time agent (full control):** Soniox STT → LLM → ElevenLabs TTS inside ScriptEngine FSM. `ConversationState` checkpointed to Redis. For deterministic slot-filling and custom barge-in.

---

## 9. Reliability, Idempotency & Governors

### 9.1 Idempotency guarantees (implemented + tested)

| Operation | Mechanism | Test |
|-----------|-----------|------|
| Claim contact | Conditional `UPDATE WHERE status='queued'` | `test_claim_contact_second_claim_returns_none` |
| Provider dial | Write-ahead session + `call_session_id` as idempotency key | — |
| Webhook ingest | `processed_events` PK + `ON CONFLICT DO NOTHING` | `test_register_event_dedup` |
| State transition | Forward-only CAS | `test_forward_only_status_absorbs_terminal` |
| Verification | Upsert on `(session_id, step)` | `test_verification_upsert_overwrites_not_duplicates` |
| Campaign start | Redlock + `start_locked` | `test_redlock_is_exclusive` |
| Domain events | Outbox `dedup_key` unique | `test_outbox_dedup_key_exactly_once` |

### 9.2 Distributed governors (implemented)

| Governor | File | Purpose |
|----------|------|---------|
| Token-bucket rate limiter | `governors/rate_limiter.py` | Per-provider API QPS (Lua atomic) |
| Concurrency semaphore | `governors/concurrency.py` | Live-call ceiling (leased sorted-set) |
| Circuit breaker | `governors/circuit_breaker.py` | Provider outage → pause dialing |
| TPM token budget | `governors/token_budget.py` | LLM surge → queue, don't blow quota |

### 9.3 Reliability patterns

| Pattern | Status |
|---------|--------|
| Exponential backoff + jitter | ✅ `reliability/backoff.py` |
| Retry classification (retryable vs terminal) | ✅ `reliability/retry.py` |
| Transactional outbox | ✅ `reliability/outbox.py` |
| Dead-letter stream | ✅ `dlq:stream` (manual replay) |
| Graceful worker shutdown | ✅ `workers/base.py` (SIGTERM drain) |
| Reconciler (stale sessions, orphan contacts) | ✅ `workers/reconciler.py` |
| Delayed retry via ZSET scheduler | ⚠️ TODO in `workers/base.py` |

### 9.4 Edge cases (PRD §12 — design vs implementation)

The PRD catalogs 48 edge cases across telephony, data pipeline, infrastructure, and compliance. Core fixes are **implemented in code** (claim lease, webhook dedup, forward-only CAS, circuit breaker, calling window, opt-out). Items requiring **production validation** include: load-test at 3k/min, chaos tests (kill worker mid-dial), contract tests with recorded provider fixtures, and number-pool rotation for spam-flagged caller IDs.

---

## 10. Compliance & Security

### Implemented

| Control | Implementation |
|---------|----------------|
| JWT HS256 auth | `control_api/security.py`; secret length validated at startup |
| Row-level ownership | Every query scoped to `owner_id` |
| Webhook HMAC verification | ElevenLabs `t,v0`, Twilio `X-Twilio-Signature`, timestamp tolerance |
| Signed context tokens | Short-lived JWT for `/exotel/call-context` (replaces bare UUID) |
| Calling-window governor | `compliance.py` — 09:00–21:00 local default (TRAI-aligned) |
| Do-not-contact / opt-out | `ContactStatus.do_not_contact`, cross-campaign suppression |
| Phone masking in feed | `domain/phone.py` `mask_e164` |
| Password hashing | argon2 via `argon2-cffi` |

### Planned / partial

| Control | Status |
|---------|--------|
| JWT revocation denylist | TODO in `auth.py` |
| Postgres RLS | Defense-in-depth, not enabled |
| IP allowlist for webhooks | Edge/WAF in production topology |
| External DND registry check | Logic exists; registry API not wired |
| AWS Secrets Manager | PRD §14.5; env injection in K8s example only |
| PII encryption at rest | Disk/TDE in production RDS |

---

## 11. Cost & Token Efficiency

Designed per PRD §19; implemented in `domain/verification.py`, `providers/llm/_openai_common.py`, `governors/token_budget.py`, `workers/verification.py`.

| Technique | Status |
|-----------|--------|
| Single LLM call (verify + extract + summary) | ✅ |
| Skip LLM on empty/no-answer/voicemail/failed | ✅ |
| Reuse ElevenLabs provider summary | ✅ |
| Prompt caching (static prefix first) | ✅ |
| Cap output tokens (`LLM_MAX_OUTPUT_TOKENS=400`) | ✅ |
| Transcript trimming (`TRANSCRIPT_MAX_TURNS`, chars/turn) | ✅ |
| Cheap model + escalate on low confidence | ✅ |
| TPM token-budget limiter | ✅ |
| Per-campaign spend ceiling auto-pause | ✅ |

---

## 12. Observability & Operations

### Implemented

| Capability | Status |
|------------|--------|
| Structured JSON logging | ✅ `logging.py` (structlog) |
| Prometheus metrics | ✅ `/metrics` on both APIs; `observability/metrics.py` |
| Correlation IDs in logs | ✅ `bind_call_context` |
| OpenTelemetry scaffolding | ⚠️ Partial — OTLP exporter TODO |
| Runbook stubs | ⚠️ `docs/runbooks/README.md` (checklists, not fleshed out) |

### Planned (PRD §13)

| Capability | Status |
|------------|--------|
| Grafana dashboards (live ops, funnel, provider health, cost, reliability) | 📋 |
| Loki / ELK log aggregation | 📋 |
| Distributed tracing (full OTLP pipeline) | 📋 |
| Paging alerts (circuit open, queue lag, DLQ depth, calls_live=0) | 📋 |
| "Big red button" global `dialing_enabled` flag | 📋 TODO |

### Key metrics exposed

`dials_initiated_total`, `dials_failed_total`, `webhook_received_total`, `webhook_dedup_hits_total`, `llm_tokens_used_total`, `cost_micros_total`, plus governor and queue lag gauges.

---

## 13. Infrastructure & Deployment

### Local development (docker-compose)

| Service | Port | Purpose |
|---------|------|---------|
| postgres | 5433 | System of record |
| pgbouncer | 6432 | Transaction pooling |
| redis | 6379 | Streams, locks, governors (AOF on) |
| minio | 9000/9001 | S3-compatible object store |
| migrate | — | Alembic upgrade head |
| seed | — | Demo user + clinic data |
| control-api | 8000 | Control-plane |
| webhook-ingest | 8001 | Webhook ingest |
| dialer-worker | — | Dial hot path |
| verification-worker | — | Post-call LLM |
| reconciler | — | Sweeper + outbox |
| frontend | 3000 | Landing + dashboard |

Default stack: **all mock providers** — no external credentials required.

### Production topology (planned — `infra/k8s/`)

| Deployment | Scaling | Status |
|------------|---------|--------|
| control-api | HPA on CPU + RPS (2–10) | Manifests exist |
| webhook-ingest | HPA on RPS (2–20) | Manifests exist |
| dialer-worker | KEDA on Redis Stream lag (3–100) | Manifests exist |
| verification-worker | KEDA on stream lag (2–40) | Manifests exist |
| reconciler | Fixed, leader-elected (1–2) | Manifests exist |
| migrate-job | Pre-deploy Alembic | Manifest exists |

**Managed services (production target):** RDS Postgres + read replica, ElastiCache Redis, S3 + Glacier, AWS Secrets Manager.

### CI/CD (`.github/workflows/ci.yml`)

| Job | What it runs | Status |
|-----|--------------|--------|
| backend | ruff + mypy + pytest (unit) | ✅ |
| integration | Idempotency suite vs Postgres + Redis | ✅ |
| frontend | `npm run build` | ✅ |
| docker | Image build + Trivy scan (report-only) | ✅ on push |

**Not yet in CI:** deploy on tag, staging smoke tests, Trivy gate (`exit-code: 0` today).

---

## 14. Testing & Quality

### Automated (current)

| Layer | Count | Coverage |
|-------|-------|----------|
| Unit tests | ~63 | Governors, idempotency SQL helpers, HMAC, phone, verification, compliance, token efficiency, circuit breaker, backoff, retry, security |
| Integration / idempotency | 7 | PRD §16.1 mandatory "run twice == run once" suite |
| Frontend build | — | `next build` in CI |
| Lint / types | — | ruff clean, mypy on `src/` |

### Manual E2E (documented in `docs/testing.md`)

```
docker compose up --build
→ http://localhost:3000/dashboard
→ Start Outbound Call
→ new query card in ~5–15s (WebSocket push)
```

### Not yet automated (PRD §16.2)

| Test type | Status |
|-----------|--------|
| Contract tests (recorded provider fixtures) | 📋 |
| Load test (3k initiations/min, failure injection) | 📋 |
| Soak test (hours-long stability) | 📋 |
| Chaos test (kill worker, Redis restart, Postgres failover) | 📋 |

**Acceptance bar (definition of done for production):** At target load with 10% injected failures and a fault during the run: zero double-dials, zero lost call records, zero duplicate verifications, full reconciliation within one sweep cycle.

---

## 15. Rollout Plan

From PRD §17 and `docs/architecture.md`:

| Phase | Scope | Exit criteria | Estimated status |
|-------|-------|---------------|------------------|
| **0 · Hardening** | Pin deps, one runtime, secure context endpoint, CI | CI green; no unauth endpoints | ✅ Largely complete |
| **1 · Core idempotency** | Atomic claim, write-ahead, webhook dedup, reconciler | Idempotency suite passes; kill-worker recovers | ✅ Suite passes; chaos not automated |
| **2 · Governors** | Token bucket, concurrency, circuit breaker, backpressure | 3k/min holds SLOs; 0 provider breaches | ⚠️ Code done; load test not run |
| **3 · Scale-out** | KEDA, PgBouncer, read-replica reports, partitioning | Soak stable; 10k/min stretch passes | ⚠️ Infra scaffolded; not validated |
| **4 · Observability + compliance** | Dashboards, alerts, runbooks, calling-window + DND + opt-out | Big-red-button works; compliance enforced | ⚠️ Partial (compliance code yes; Grafana no) |
| **5 · Pilot** | One real client, capped concurrency | Clean week at production load | 📋 Not started |

---

## 16. Known Gaps & TODOs

Consolidated from code `TODO` comments, README, and PRD non-goals.

### Code TODOs (in-repo)

| Location | Gap |
|----------|-----|
| `contacts.py` | Large-file async ingest (S3 + worker); rejected_rows artifact to S3 |
| `recordings.py` | S3 presigned GET URLs |
| `reports.py` | CSV/XLSX export from read replica |
| `call_sessions.py` | Manual re-verify → enqueue verify stream |
| `ws.py` | Live transcript stream (LiveKit path) |
| `context.py` | Minimal SIP connect params |
| `reconciler.py` | Provider-specific adapter selection; real event bus publish |
| `auth.py` | JWT revocation denylist in Redis |
| `workers/base.py` | Delayed retry via ZSET scheduler |
| `tracing.py` | OTLP span exporter |
| `anthropic.py` | Full adapter (raises `NotImplementedError`) |
| `telephony/factory.py` | Plivo, Telnyx raise `NotImplementedError` |
| `runbooks/README.md` | Global `dialing_enabled` flag |

### Product / demo gaps

| Gap | Impact |
|-----|--------|
| Landing page uses placeholder phone number | Highest-converting demo asset not live |
| No real inbound call wired end-to-end in default compose | Portfolio "call it now" incomplete |
| Recording playback in dashboard | Needs S3 presign implementation |
| Campaign management UI | API exists; no frontend |
| Multi-tenant admin, billing, settings | Explicitly out of demo scope |

### Non-goals (by design)

- Not a CRM
- Not a general DTMF IVR builder (DTMF capture supported, not a tree builder)
- Not a real-time human contact center (no agent desktop; warm transfer is a terminal action)

---

## 17. Scale Targets & SLOs (Planned Production)

These are **engineering targets from the PRD**, not yet validated by load tests.

### Throughput

| Metric | Target | Stretch |
|--------|--------|---------|
| Call initiations / minute | 3,000 | 10,000 |
| Concurrent live calls | 5,000 | 15,000 |
| Contacts ingested / upload | 1,000,000 | 5,000,000 |
| Webhook events / second | 500 | 2,000 |
| Post-call verifications / minute | 3,000 | 10,000 |

### Latency (p50 / p99)

| Operation | p50 | p99 |
|-----------|-----|-----|
| Contact claim | < 5 ms | < 30 ms |
| Dial dispatch | < 200 ms | < 1 s |
| Webhook ACK | < 50 ms | < 200 ms |
| Post-call verification | < 8 s | < 30 s |
| Live turn latency (STT→LLM→TTS) | < 800 ms | < 1.5 s |

### Reliability

- Call-record durability: **99.999%**
- Idempotency guarantee: **100%**
- Control-plane availability: **99.9%** monthly
- Data-plane degrades gracefully (pause new dials, never drop live calls)

---

## 18. Related Documents

| Document | Purpose |
|----------|---------|
| [`PRD_Callwise_Production.md`](../PRD_Callwise_Production.md) | Full product + engineering spec (private sales doc) |
| [`architecture.md`](architecture.md) | System overview and rollout phases |
| [`data-model.md`](data-model.md) | Postgres tables and retention |
| [`idempotency.md`](idempotency.md) | Master idempotency design |
| [`vendors.md`](vendors.md) | Provider matrix and documentation links |
| [`testing.md`](testing.md) | Full application testing guide |
| [`runbooks/README.md`](runbooks/README.md) | Operational procedures (stubs) |
| [`README.md`](../README.md) | Quickstart and repo status |

---

## Appendix — Demo Credentials & URLs

| Item | Value |
|------|-------|
| Demo user | `demo@callwise.dev` / `demo12345` |
| Dashboard | http://localhost:3000/dashboard |
| Control API docs | http://localhost:8000/docs |
| Webhook ingest docs | http://localhost:8001/docs |
| Quickstart | `docker compose up --build` |

---

*This document reflects the repository as of June 2026. For the authoritative engineering spec and sales positioning, see `PRD_Callwise_Production.md`. For implementation truth, prefer code + tests over this document when they diverge.*
