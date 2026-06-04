# Idempotency — the master design

Telephony, webhooks, and distributed queues are all **at-least-once**. Every
business-effecting operation is therefore idempotent: running it twice equals running it
once. Implementation lives in `backend/src/callwise/domain/idempotency.py` and is covered
by the mandatory "run twice == run once" suite (`tests/integration/test_idempotency.py`).

| Operation | Mechanism | Duplicate effect |
|---|---|---|
| Claim contact | Conditional `UPDATE ... WHERE status='queued'` | Second claim returns nothing; no double-dial |
| Provider dial | `call_session_id` idempotency key + write-ahead row + pre-check | No second call placed |
| Webhook ingest | `processed_events` PK + `ON CONFLICT DO NOTHING` | Duplicate ACKed, ignored |
| State transition | Forward-only CAS on status | Re-apply is a no-op |
| Verification write | Upsert on `(call_session_id, step)` | Overwrite, never duplicate |
| Campaign start | Redlock + `start_locked` flag | No-op returns current state |
| Domain event | Outbox row keyed on `(aggregate_id, event_type)` | Emitted exactly once downstream |

## Why the claim has a lease

`contacts.lease_expires_at` makes the claim **self-healing**. If a worker crashes after
claiming but before dialing, the contact would otherwise be stuck `in_progress` forever.
The reconciler reclaims any `in_progress` contact whose lease expired and has no live
`call_session`, returning it to `queued`.

## Why a leased sorted-set for concurrency

A plain `INCR/DECR` counter leaks a slot forever if a worker crashes between increment and
decrement. The concurrency governor uses a Redis sorted set scored by lease expiry; expired
holders are pruned on each acquire, so the live-call count is always eventually accurate.

## The edge-case rule

Every external boundary (provider, webhook, queue, DB) is treated as **unreliable and
adversarial**: signatures verified, payloads validated, effects made idempotent, timeouts
on everything, and a reconciler that assumes any in-flight thing might be silently lost.

See PRD §6 and §12 for the full catalog.
