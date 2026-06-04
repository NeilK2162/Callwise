"""SQLAlchemy ORM models — the Callwise data model (PRD §10).

Conventions:
  * UUID primary keys (generated app-side; `call_sessions.id` doubles as the provider
    idempotency key, PRD §6.2).
  * Enums stored as VARCHAR + CHECK (`native_enum=False`) so they're trivial to evolve.
  * High-churn tables (`call_events`, `processed_events`) are range-partitioned by month
    in production (PRD §10.4); the partition DDL lives in migrations, not here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from callwise.db.base import Base
from callwise.db.enums import (
    CallDirection,
    CallStatus,
    CampaignStatus,
    ContactStatus,
    VerificationOutcome,
)


def _uuid_col(*, primary_key: bool = False) -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=primary_key, default=uuid.uuid4
    )


def _ts(*, default_now: bool = False) -> Mapped[datetime]:
    kwargs: dict = {}
    if default_now:
        kwargs["server_default"] = func.now()
    return mapped_column(DateTime(timezone=True), **kwargs)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_col(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _ts(default_now=True)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = _uuid_col(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, native_enum=False, length=20),
        default=CampaignStatus.draft,
        index=True,
    )
    direction: Mapped[CallDirection] = mapped_column(
        Enum(CallDirection, native_enum=False, length=10), default=CallDirection.outbound
    )

    # Pacing / provider config (PRD §5.2)
    provider: Mapped[str] = mapped_column(String(40), default="mock")
    agent_id: Mapped[str | None] = mapped_column(String(120))
    max_concurrent_calls: Mapped[int] = mapped_column(Integer, default=100)
    dials_per_minute: Mapped[int] = mapped_column(Integer, default=60)
    max_attempts_per_contact: Mapped[int] = mapped_column(Integer, default=3)
    default_country_code: Mapped[str] = mapped_column(String(4), default="IN")

    # Calling window (per contact timezone) + retry backoff config
    dial_window: Mapped[dict] = mapped_column(JSONB, default=dict)
    retry_backoff: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Spend ceiling / accounting (PRD §9.3, §14.4)
    spend_ceiling_micros: Mapped[int | None] = mapped_column(BigInteger)
    spent_micros: Mapped[int] = mapped_column(BigInteger, default=0)

    meta: Mapped[dict] = mapped_column(JSONB, default=dict)  # start_locked, started_at...
    created_at: Mapped[datetime] = _ts(default_now=True)
    updated_at: Mapped[datetime] = _ts(default_now=True)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        # Fast claim scans — partial index on the only status the dialer claims from.
        Index(
            "ix_contacts_claimable",
            "campaign_id",
            postgresql_where=text("status = 'queued'"),
        ),
        # Reconciler stale-lease sweeps (PRD §5.6).
        Index("ix_contacts_lease", "status", "lease_expires_at"),
        CheckConstraint("attempt_count >= 0", name="ck_contacts_attempts_nonneg"),
    )

    id: Mapped[uuid.UUID] = _uuid_col(primary_key=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    phone_e164: Mapped[str] = mapped_column(String(20), index=True)
    customer_name: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(12), default="en-IN")
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Kolkata")

    status: Mapped[ContactStatus] = mapped_column(
        Enum(ContactStatus, native_enum=False, length=20),
        default=ContactStatus.queued,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)

    # Self-healing claim lease (PRD §6.1)
    claimed_by: Mapped[str | None] = mapped_column(String(80))
    claimed_at: Mapped[datetime | None] = _ts()
    lease_expires_at: Mapped[datetime | None] = _ts()

    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict)  # vertical-specific
    outcome_tags: Mapped[dict] = mapped_column(JSONB, default=dict)  # written by verify
    last_outcome: Mapped[str | None] = mapped_column(String(40))  # retry-aware opening

    created_at: Mapped[datetime] = _ts(default_now=True)


class ContextSnapshot(Base):
    """Immutable per-attempt context (PRD §7.1). Never UPDATEd — corrections create a new
    snapshot for the next attempt."""

    __tablename__ = "context_snapshots"

    id: Mapped[uuid.UUID] = _uuid_col(primary_key=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    # Frozen contact data
    customer_name: Mapped[str | None] = mapped_column(String(200))
    phone_e164: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(12))
    custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Frozen agent config
    agent_id: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    script_flow_id: Mapped[str | None] = mapped_column(String(80))
    dynamic_variables: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Guardrails
    max_call_duration_s: Mapped[int] = mapped_column(Integer, default=300)
    allowed_actions: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = _ts(default_now=True)


class CallSession(Base):
    __tablename__ = "call_sessions"
    __table_args__ = (
        # provider_call_id unique where not null — guards duplicate mapping (edge #40).
        Index(
            "uq_call_sessions_provider_call_id",
            "provider_call_id",
            unique=True,
            postgresql_where=text("provider_call_id IS NOT NULL"),
        ),
        Index("ix_call_sessions_stale", "status", "started_at"),
        Index("ix_call_sessions_contact", "contact_id"),
    )

    # id IS the idempotency key passed to the provider (PRD §6.2).
    id: Mapped[uuid.UUID] = _uuid_col(primary_key=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE")
    )
    context_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("context_snapshots.id", ondelete="SET NULL")
    )
    direction: Mapped[CallDirection] = mapped_column(
        Enum(CallDirection, native_enum=False, length=10), default=CallDirection.outbound
    )
    provider: Mapped[str] = mapped_column(String(40))
    provider_call_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus, native_enum=False, length=20), default=CallStatus.dialing
    )

    started_at: Mapped[datetime] = _ts(default_now=True)
    answered_at: Mapped[datetime | None] = _ts()
    ended_at: Mapped[datetime | None] = _ts()
    duration_s: Mapped[int | None] = mapped_column(Integer)
    end_reason: Mapped[str | None] = mapped_column(String(40))
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class CallEvent(Base):
    """Append-only provider/status events — range-partitioned by month in prod."""

    __tablename__ = "call_events"
    __table_args__ = (Index("ix_call_events_session", "call_session_id", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_col(primary_key=True)
    call_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _ts(default_now=True)


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = _uuid_col(primary_key=True)
    call_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), unique=True
    )
    turns: Mapped[list] = mapped_column(JSONB, default=list)  # [{role, text, ts}, ...]
    summary: Mapped[str | None] = mapped_column(Text)  # one-shot summary (PRD §5.5)
    s3_key: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = _ts(default_now=True)


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[uuid.UUID] = _uuid_col(primary_key=True)
    call_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE"), index=True
    )
    s3_key: Mapped[str | None] = mapped_column(String(512))
    duration_s: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(40), default="audio/mpeg")
    uploaded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _ts(default_now=True)


class CallVerification(Base):
    """Post-call LLM verification. Upserted on (call_session_id, step) — re-runs overwrite,
    never duplicate (PRD §6.3)."""

    __tablename__ = "call_verifications"
    __table_args__ = (
        UniqueConstraint("call_session_id", "step", name="uq_verification_session_step"),
    )

    id: Mapped[uuid.UUID] = _uuid_col(primary_key=True)
    call_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("call_sessions.id", ondelete="CASCADE")
    )
    step: Mapped[str] = mapped_column(String(40), default="verify")
    outcome: Mapped[VerificationOutcome] = mapped_column(
        Enum(VerificationOutcome, native_enum=False, length=30),
        default=VerificationOutcome.undetermined,
    )
    responder_type: Mapped[str | None] = mapped_column(String(30))  # human/machine/unknown
    extracted: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float | None] = mapped_column()
    result: Mapped[dict] = mapped_column(JSONB, default=dict)  # full raw LLM result
    created_at: Mapped[datetime] = _ts(default_now=True)
    updated_at: Mapped[datetime] = _ts(default_now=True)


class ProcessedEvent(Base):
    """Webhook dedup table — INSERT ... ON CONFLICT DO NOTHING makes duplicates no-ops
    (PRD §6.3). Range-partitioned by month + pruned after 30 days in prod."""

    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str] = mapped_column(String(40))
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    received_at: Mapped[datetime] = _ts(default_now=True)


class Outbox(Base):
    """Transactional outbox for exactly-once domain-event publishing (PRD §9.5).
    The state change and the outbox insert share one transaction; a dispatcher polls
    unpublished rows. `dedup_key` UNIQUE guarantees exactly-once downstream."""

    __tablename__ = "outbox"
    __table_args__ = (
        Index(
            "ix_outbox_unpublished",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))  # call_session_id
    event_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    dedup_key: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = _ts(default_now=True)
    published_at: Mapped[datetime | None] = _ts()


class IngestJob(Base):
    """Async CSV/XLSX ingest job — progress reported over WebSocket (PRD §5.1)."""

    __tablename__ = "ingest_jobs"

    id: Mapped[uuid.UUID] = _uuid_col(primary_key=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    s3_key: Mapped[str | None] = mapped_column(String(512))
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0)
    rejected_rows_key: Mapped[str | None] = mapped_column(String(512))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts(default_now=True)
    updated_at: Mapped[datetime] = _ts(default_now=True)


class Suppression(Base):
    """Do-not-contact / DNC suppression list (PRD §14.2, edge cases #42, #43).

    Honored across ALL of an owner's campaigns: an opt-out on one call suppresses the
    number everywhere. Checked pre-dial in the dialer."""

    __tablename__ = "suppressions"
    __table_args__ = (
        UniqueConstraint("owner_id", "phone_e164", name="uq_suppression_owner_phone"),
    )

    id: Mapped[uuid.UUID] = _uuid_col(primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    phone_e164: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str] = mapped_column(String(40), default="opt_out")
    created_at: Mapped[datetime] = _ts(default_now=True)
