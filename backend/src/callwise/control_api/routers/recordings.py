"""Recording playback — presigned URLs with short expiry (PRD §11.1, §14.5)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from callwise.control_api.deps import CurrentUser, DbSession
from callwise.db.models import Recording

router = APIRouter()


@router.get("/{recording_id}/url")
async def presigned_url(
    recording_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> dict[str, str]:
    rec = await db.get(Recording, recording_id)
    if rec is None or rec.s3_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recording not available")
    # TODO: generate an S3 presigned GET URL with short expiry (e.g. 300s) scoped to owner.
    return {"url": f"s3://{rec.s3_key}", "expires_in": "300"}
