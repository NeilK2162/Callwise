"""Pydantic request/response models for the control-plane API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from callwise.db.enums import (
    CallDirection,
    CallStatus,
    CampaignStatus,
    ContactStatus,
    VerificationOutcome,
)


# --- Auth ---
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# --- Campaigns ---
class CampaignCreate(BaseModel):
    name: str
    direction: CallDirection = CallDirection.outbound
    provider: str = "mock"
    agent_id: str | None = None
    max_concurrent_calls: int = 100
    dials_per_minute: int = 60
    max_attempts_per_contact: int = 3
    default_country_code: str = "IN"


class CampaignOut(BaseModel):
    id: uuid.UUID
    name: str
    status: CampaignStatus
    direction: CallDirection
    provider: str
    max_concurrent_calls: int
    dials_per_minute: int
    spent_micros: int
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Contacts / ingest ---
class UploadResponse(BaseModel):
    job_id: uuid.UUID
    campaign_id: uuid.UUID
    status: str


class JobOut(BaseModel):
    id: uuid.UUID
    status: str
    total_rows: int
    imported_rows: int
    rejected_rows_key: str | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


class ContactOut(BaseModel):
    id: uuid.UUID
    phone_e164: str
    customer_name: str | None
    status: ContactStatus
    attempt_count: int
    last_outcome: str | None
    outcome_tags: dict

    model_config = {"from_attributes": True}


# --- Calls / verification / transcript ---
class VerificationOut(BaseModel):
    outcome: VerificationOutcome
    responder_type: str | None
    confidence: float | None
    extracted: dict

    model_config = {"from_attributes": True}


class CallSessionOut(BaseModel):
    id: uuid.UUID
    direction: CallDirection
    status: CallStatus
    provider: str
    started_at: datetime
    duration_s: int | None
    end_reason: str | None

    model_config = {"from_attributes": True}


# --- Dashboard (the query card, PRD §0.4) ---
class QueryCard(BaseModel):
    call_session_id: uuid.UUID
    direction: CallDirection
    phone_masked: str
    customer_name: str | None
    started_at: datetime
    summary: str | None
    outcome: VerificationOutcome | None
    confidence: float | None
    extracted: dict
    duration_s: int | None
    has_recording: bool


class ReportSummary(BaseModel):
    calls_today: int
    booked: int
    callback_needed: int
    missed: int
    avg_duration_s: float


class OutboundCallRequest(BaseModel):
    phone: str
    campaign_id: uuid.UUID | None = None
    customer_name: str | None = None


class OutboundAck(BaseModel):
    status: str
    contact_id: uuid.UUID
    campaign_id: uuid.UUID
