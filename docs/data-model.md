# Data model

Defined in `backend/src/callwise/db/models.py`; migrated by `backend/alembic/`.

```
users ──< campaigns ──< contacts ──< call_sessions ──< call_events
                              │             │
                              │             ├──< transcripts (1:1)
                              │             ├──< recordings
                              │             └──< call_verifications  (unique: session, step)
                              │
context_snapshots (1 per dial attempt, immutable)
processed_events  (webhook dedup, PK = event_id)
outbox            (exactly-once event publishing, unique dedup_key)
ingest_jobs       (async CSV/XLSX import progress)
```

## Key tables

- **contacts** — the dial unit. Carries `status`, `attempt_count`, and the self-healing
  claim lease (`claimed_by`, `claimed_at`, `lease_expires_at`). Partial index on
  `status='queued'` for fast claim scans; `(status, lease_expires_at)` for reconciler sweeps.
- **call_sessions** — one per dial attempt; `id` doubles as the provider idempotency key.
  `provider_call_id` is unique-where-not-null. Status transitions are forward-only.
- **context_snapshots** — immutable freeze of contact data + agent config at dial time, so
  in-flight calls keep the version they started with.
- **call_verifications** — post-call LLM result, unique on `(call_session_id, step)` so
  re-runs upsert.
- **processed_events** / **outbox** — the idempotency + exactly-once plumbing.

## State machines

- **Contact:** `queued → in_progress → {completed | no_answer | failed | dnd}`;
  `no_answer/failed → queued` while attempts remain → `max_attempts`.
- **Call session:** `dialing → ringing → in_progress → {completed | voicemail}`, or
  `dialing → {no_answer | busy | failed | canceled}`. Forward-only (CAS).

## Partitioning & retention (production)

`call_events` and `processed_events` are range-partitioned by month; old partitions are
detached and archived to S3. `processed_events` retained 30 days; `outbox` published rows
pruned after 7 days; transcripts/recordings per client contract (hot → Glacier). See
PRD §10.4–§10.5.
