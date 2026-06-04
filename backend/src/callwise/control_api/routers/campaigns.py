"""Campaign lifecycle (PRD §5.2, §11.1). Start is idempotent and locked (§6.4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from callwise.control_api.deps import CurrentUser, DbSession, owned_or_404
from callwise.control_api.schemas import CampaignCreate, CampaignOut
from callwise.db.enums import CampaignStatus
from callwise.db.models import Campaign
from callwise.locks import redlock
from callwise.logging import get_logger
from callwise.orchestration import enqueue_dials_for_campaign
from callwise.queue.factory import get_queue
from callwise.redis_pool import get_redis

router = APIRouter()
log = get_logger(__name__)


async def _get_owned(db: DbSession, campaign_id: uuid.UUID, user: CurrentUser) -> Campaign:
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    owned_or_404(campaign.owner_id, user)
    return campaign


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(body: CampaignCreate, db: DbSession, user: CurrentUser) -> Campaign:
    campaign = Campaign(owner_id=user.id, **body.model_dump())
    db.add(campaign)
    await db.commit()
    return campaign


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(db: DbSession, user: CurrentUser) -> list[Campaign]:
    stmt = select(Campaign).order_by(Campaign.created_at.desc())
    if not user.is_superuser:
        stmt = stmt.where(Campaign.owner_id == user.id)
    return list(await db.scalars(stmt))


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(campaign_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Campaign:
    return await _get_owned(db, campaign_id, user)


@router.post("/{campaign_id}/start", response_model=CampaignOut)
async def start_campaign(campaign_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Campaign:
    """Idempotent + locked: a re-invocation is a no-op returning current state (PRD §6.4)."""
    campaign = await _get_owned(db, campaign_id, user)
    redis = get_redis()
    async with redlock(redis, f"campaign-start:{campaign_id}", ttl_ms=30_000) as locked:
        if not locked:
            return campaign  # someone else is starting it
        if campaign.meta.get("start_locked"):
            return campaign  # already started; no-op
        campaign.meta = {
            **campaign.meta,
            "start_locked": True,
            "started_at": datetime.now(UTC).isoformat(),
        }
        campaign.status = CampaignStatus.running
        await db.commit()
        # Enqueue dials in paced batches; the claim is idempotent so this is retry-safe.
        enqueued = await enqueue_dials_for_campaign(db, get_queue(), campaign=campaign)
        log.info("campaign_started", campaign_id=str(campaign_id), enqueued=enqueued)
    return campaign


@router.post("/{campaign_id}/pause", response_model=CampaignOut)
async def pause_campaign(campaign_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Campaign:
    campaign = await _get_owned(db, campaign_id, user)
    campaign.status = CampaignStatus.paused
    await db.commit()
    return campaign


@router.post("/{campaign_id}/resume", response_model=CampaignOut)
async def resume_campaign(campaign_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Campaign:
    campaign = await _get_owned(db, campaign_id, user)
    campaign.status = CampaignStatus.running
    await db.commit()
    return campaign


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(campaign_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    campaign = await _get_owned(db, campaign_id, user)
    await db.delete(campaign)
    await db.commit()
