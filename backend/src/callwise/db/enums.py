"""Domain enums and their state machines (PRD §10.3)."""

from __future__ import annotations

from enum import StrEnum


class CampaignStatus(StrEnum):
    draft = "draft"
    scheduled = "scheduled"
    running = "running"
    paused = "paused"
    completed = "completed"
    archived = "archived"


class ContactStatus(StrEnum):
    """`queued → in_progress → {completed | no_answer | failed | dnd}`;
    `no_answer/failed → queued` while attempts remain → eventually `max_attempts`."""

    queued = "queued"
    in_progress = "in_progress"
    completed = "completed"
    no_answer = "no_answer"
    failed = "failed"
    dnd = "dnd"
    max_attempts = "max_attempts"
    do_not_contact = "do_not_contact"  # permanent opt-out (PRD §14.2)


class CallStatus(StrEnum):
    """Forward-only (CAS, PRD §6.3). Terminal states absorb earlier ones."""

    dialing = "dialing"
    ringing = "ringing"
    in_progress = "in_progress"
    completed = "completed"
    voicemail = "voicemail"
    no_answer = "no_answer"
    busy = "busy"
    failed = "failed"
    canceled = "canceled"


TERMINAL_CALL_STATUSES: frozenset[CallStatus] = frozenset(
    {
        CallStatus.completed,
        CallStatus.voicemail,
        CallStatus.no_answer,
        CallStatus.busy,
        CallStatus.failed,
        CallStatus.canceled,
    }
)


class CallDirection(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class VerificationOutcome(StrEnum):
    """Plain-English outcome tags surfaced on the query card (PRD §0.4)."""

    appointment_booked = "appointment_booked"
    question_answered = "question_answered"
    callback_needed = "callback_needed"
    not_interested = "not_interested"
    wrong_number = "wrong_number"
    wrong_party = "wrong_party"
    voicemail = "voicemail"
    opt_out = "opt_out"
    undetermined = "undetermined"
