# Runbooks

Each procedure is a checklist, not tribal knowledge (PRD §13.4). Stubs to flesh out as the
system goes live.

## Big red button — pause all campaigns
1. `POST /api/campaigns/{id}/pause` for each running campaign, or set the global
   `dialing_enabled=false` flag (TODO: add flag).
2. Live calls continue; the queue holds in `queued`. Verify `calls_live` trends to 0 as
   calls end.

## Provider outage
1. Confirm the circuit breaker opened (`circuit_breaker_state{provider}=2`).
2. Dialing for that provider auto-pauses; the queue holds. Do **not** flush the queue.
3. The breaker auto-probes after cooldown. If the outage is prolonged, switch
   `TELEPHONY_PROVIDER` to a backup and redeploy workers.

## Redis failover
1. Locks have TTLs (auto-release); rate-limit buckets rebuild; conv-state is checkpointed.
2. New dials pause until Redis is healthy. Confirm streams + consumer groups exist
   post-recovery (`XINFO GROUPS`).

## Postgres failover
1. Writes fail briefly; idempotency makes retried writes safe.
2. Confirm reads route to the replica and the primary endpoint updated.

## DLQ drain / replay
1. Inspect `dlq:stream` (`XRANGE dlq:stream - +`).
2. After fixing the root cause, re-publish entries to their origin stream and `XDEL` from
   the DLQ.

## Cost runaway
1. Check `cost_micros_total{campaign}` vs ceiling. Campaigns auto-pause at the ceiling.
2. Investigate `dials_failed_total{reason}` for redial loops; verify retry classification.
