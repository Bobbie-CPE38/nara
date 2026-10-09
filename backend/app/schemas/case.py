"""Answers of the case read routes (docs/workflow.md, section 9.3)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.domain.enums import (
    ActorType,
    AuditAction,
    CandidateSource,
    CaseStatus,
    EntityType,
    OutreachStatus,
)


class GapCount(BaseModel):
    """One role or skill of a gap. `id` is the role ID or the skill ID."""

    id: int
    name: str
    required_count: int
    current_count: int
    gap_count: int


class GapView(BaseModel):
    id: int
    headcount_gap: int
    computed_at: datetime
    roles: list[GapCount]
    skills: list[GapCount]


class CandidateView(BaseModel):
    candidate_item_id: int
    rank: int
    staff_id: int
    first_name: str
    last_name: str
    source: CandidateSource
    # null until an offer was created for this candidate
    outreach_status: OutreachStatus | None


class CaseDetail(BaseModel):
    """GET /cases/{id}. `status` is the key the E2E test reads."""

    id: int
    status: CaseStatus
    event_id: int
    shift_id: int
    required_replacement_time: datetime
    created_at: datetime
    updated_at: datetime
    # null until the ASSESSING step stored a gap
    gap: GapView | None
    # Empty until the solver stored a plan. Ordered by rank
    candidates: list[CandidateView]


class AuditEntry(BaseModel):
    """One item of GET /cases/{id}/audit. `action` is the key the E2E test reads."""

    id: int
    action: AuditAction
    actor_id: int
    actor_name: str
    actor_type: ActorType
    entity_type: EntityType
    entity_id: int | None
    payload: dict[str, Any]
    created_at: datetime
