"""Recording playback — presigned URLs with short expiry (PRD §11.1, §14.5)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse

from callwise.control_api.deps import CurrentUser, DbSession, owned_or_404
from callwise.db.models import CallSession, Campaign, Contact, Recording
from callwise.storage import get_object_store

router = APIRouter()


async def _owned_recording(db, recording_id: uuid.UUID, user: CurrentUser) -> Recording:
    rec = await db.get(Recording, recording_id)
    if rec is None or rec.s3_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recording not available")
    sess = await db.get(CallSession, rec.call_session_id)
    contact = await db.get(Contact, sess.contact_id) if sess else None
    campaign = await db.get(Campaign, contact.campaign_id) if contact else None
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recording not available")
    owned_or_404(campaign.owner_id, user)
    return rec


async def _url_for(rec: Recording) -> str:
    # Demo/local placeholders (mock provider) aren't in our bucket — return as-is.
    if rec.s3_key.startswith(("mock://", "s3://", "http://", "https://")):
        return rec.s3_key
    return await get_object_store().presigned_get(rec.s3_key, expires=300)


@router.get("/{recording_id}/url")
async def presigned_url(recording_id: uuid.UUID, db: DbSession, user: CurrentUser) -> dict[str, str]:
    rec = await _owned_recording(db, recording_id, user)
    return {"url": await _url_for(rec), "expires_in": "300"}


@router.get("/{recording_id}/download")
async def download(recording_id: uuid.UUID, db: DbSession, user: CurrentUser) -> RedirectResponse:
    rec = await _owned_recording(db, recording_id, user)
    return RedirectResponse(url=await _url_for(rec))
