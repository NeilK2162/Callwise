"""initial schema

Builds the full Callwise schema (PRD §10) from the SQLAlchemy model metadata, including
the partial indexes for fast claim scans + reconciler sweeps and the unique constraints
that back the idempotency guarantees. Subsequent migrations use
`alembic revision --autogenerate`.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

import callwise.db.models  # noqa: F401  (populate Base.metadata)
from callwise.db.base import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
