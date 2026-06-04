"""The mandatory idempotency suite (PRD §16.1).

For every business operation, assert **run twice == run once**. These require a live
Postgres + Redis, so they're skipped unless `CALLWISE_IT_DB` is set (CI provides a
service container; locally run against the docker-compose Postgres).

This file is the scaffold + checklist; fill in the bodies as each path lands (Phase 1 of
the rollout, PRD §17).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("CALLWISE_IT_DB"),
    reason="integration DB not configured (set CALLWISE_IT_DB)",
)


@pytest.mark.skip(reason="TODO: implement against a live DB in Phase 1")
async def test_claim_contact_double_claim_no_double_dial():
    """Two concurrent claims on one queued contact: exactly one wins, the other gets None."""


@pytest.mark.skip(reason="TODO: implement against a live DB in Phase 1")
async def test_webhook_dedup_double_delivery_is_noop():
    """Same event_id ingested twice → second is ACKed and ignored (processed_events PK)."""


@pytest.mark.skip(reason="TODO: implement against a live DB in Phase 1")
async def test_verification_upsert_overwrites_not_duplicates():
    """Re-running verify for one session updates the single (session, step) row."""


@pytest.mark.skip(reason="TODO: implement against a live DB in Phase 1")
async def test_forward_only_status_transition_absorbs_terminal():
    """Re-applying a terminal status is a no-op; earlier states can't overwrite later ones."""


@pytest.mark.skip(reason="TODO: implement against a live DB in Phase 1")
async def test_campaign_start_is_idempotent():
    """Two starts → one set of dials enqueued; second returns current state."""


@pytest.mark.skip(reason="TODO: implement against a live DB in Phase 1")
async def test_outbox_publishes_exactly_once():
    """Dispatcher retries don't double-publish — dedup_key UNIQUE holds."""
