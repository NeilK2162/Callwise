# Callwise — Architecture

> The full spec is `PRD_Callwise_Production.md` (untracked). This doc is the tracked,
> standalone summary engineers work from.

## Two faces, one machine

- **Shop window (Part A):** inbound/outbound AI voice agent → a dashboard where every call
  is a tagged, searchable *query card*. This is what sells. (`frontend/`)
- **Delivery engine (Part B):** the system that makes it real at thousands of concurrent
  calls/minute. (`backend/`, `infra/`)

**Core principle:** *initiations are elastic; live calls are sacred.* Under stress the
system stops starting new calls (sheds at the queue) but never drops a live call and never
loses its record.

## Components

```
            ┌──────────────┐        ┌─────────────────┐
  clients → │ control-api  │        │ webhook-ingest  │ ← telephony/conversation providers
            │ (FastAPI)    │        │ (FastAPI)       │
            └──────┬───────┘        └────────┬────────┘
                   │ enqueue                  │ verify HMAC → dedup → enqueue → ACK 200
        ┌──────────┴───────────── Redis Streams (broker) ──────────┐
        │                          │                                │
   dial:stream                verify:stream                   (outbox via reconciler)
        │                          │                                │
 ┌──────▼───────┐         ┌────────▼─────────┐           ┌──────────▼─────────┐
 │ dialer-worker│         │ verification-    │           │ reconciler         │
 │ claim→dial   │         │ worker (LLM)     │           │ sweep + outbox     │
 └──────┬───────┘         └──────────────────┘           └────────────────────┘
        │ governed dispatch (token bucket · concurrency · circuit breaker)
        ▼
   telephony + conversation providers (Exotel/Twilio · ElevenLabs/LiveKit)

  Postgres (via PgBouncer txn pooling) · Redis (locks, governors, state) · S3 (audio/transcripts)
```

Two API deployments are scaled **independently** so webhook bursts never starve report
queries. Workers are **sharded by concern** (dialing vs verification vs reconciliation) so
a backlog in one never slows another.

## Two hot paths

**Dial path** (`workers/dialer.py`): claim a contact with an atomic conditional UPDATE →
write-ahead a `call_session` row → acquire a concurrency slot + a provider rate-limit token
→ place the call with `call_session_id` as the idempotency key. Out of capacity → release
and re-queue (never drop).

**Post-call path** (`webhook_ingest` → `workers/verification.py`): verify HMAC → dedup via
`processed_events` → enqueue → assemble transcript → verify with the LLM (one customer, one
call, strict JSON) → upsert verification → tag the contact → emit the domain event via the
outbox.

The **reconciler** assumes the telephony world is lossy: it sweeps stale sessions (querying
the provider for true state), recovers orphaned contacts, and dispatches the outbox.

## Provider pluggability

Three factory-backed seams (`backend/src/callwise/providers/`): telephony, conversation,
LLM. The default stack is **mock** (no external creds) for local dev and the load/chaos
harness. Switch via `TELEPHONY_PROVIDER` / `CONVERSATION_PROVIDER` / `LLM_PROVIDER`.

See [`vendors.md`](vendors.md) for every external vendor, implementation status, and
official documentation URLs.

## Cost & token efficiency

The LLM verification call is the dominant variable cost at scale, so it's designed lean
(full detail in PRD §19):

- **One call per answered call** — classification, slot extraction, and the one-line
  summary come from a single Structured-Outputs completion (no separate summarize call).
- **Skip the LLM when the answer is free** — empty/agent-only transcripts and
  no-answer/busy/voicemail/failed never reach the model; ElevenLabs' provider summary is
  reused.
- **Prompt caching** — the static system+schema prefix is sent first so the provider
  caches it across the thousands of calls/min; **output is capped** (`LLM_MAX_OUTPUT_TOKENS`).
- **Transcript trimming** — long calls keep only the decision-relevant turns.
- **Cheap model + escalate on low confidence** — verify with a small model, re-verify with
  a strong one only when unsure.
- **Spend governors** — a Redis **TPM token-budget limiter** (`governors/token_budget.py`)
  queues under surge, and `response.usage` accrues into a **per-campaign spend ceiling**
  that auto-pauses the campaign.

## Rollout

| Phase | Scope | Exit criteria |
|---|---|---|
| 0 · Hardening | Pin deps, one runtime, secure context endpoint, CI | CI green; no unauth endpoints |
| 1 · Core idempotency | Atomic claim, write-ahead, webhook dedup, reconciler | Idempotency suite passes; kill-worker recovers |
| 2 · Governors | Token bucket, concurrency, circuit breaker, backpressure | 3k/min holds SLOs; 0 provider breaches |
| 3 · Scale-out | KEDA, PgBouncer, read-replica reports, partitioning | Soak stable; 10k/min stretch passes |
| 4 · Observability + compliance | Dashboards, alerts, runbooks, calling-window + DND + opt-out | Big-red-button works; compliance enforced |
| 5 · Pilot | One real client, capped concurrency | Clean week at production load |
