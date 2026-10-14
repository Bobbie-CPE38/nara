"""Answers of the case read routes (docs/workflow.md, section 9.3)."""

from typing import Any, Literal

from pydantic import BaseModel

from app.domain.enums import (
    ActorType,
    AuditAction,
    CandidateSource,
    CaseStatus,
    EntityType,
    OutreachStatus,
)
from app.schemas.types import AppDatetime


class GapCount(BaseModel):
    """One role or skill of a gap. `id` is the role ID or the skill ID."""

    id: int
    name: str
    required_count: int
    current_count: int
    gap_count: int


class GapView(BaseModel):
    id: int
    # The headcount target the gap was measured against, stored with the gap row
    effective_minimum: int
    headcount_gap: int
    computed_at: AppDatetime
    roles: list[GapCount]
    skills: list[GapCount]


# Where a candidate is in the case (docs/workflow.md, section 4.1). Computed
# from the candidate's rows when the case is read, never stored
CandidateStage = Literal[
    "NOT_CONTACTED",
    "OFFER_PENDING",
    "OFFER_SENT",
    "OFFER_REJECTED",
    "OFFER_TIMEOUT",
    "OFFER_FAILED",
    "OFFER_CANCELLED",
    "ACCEPTED",
    "SAFETY_FAILED",
    "WAITING_APPROVAL",
    "APPROVAL_REJECTED",
    "APPROVAL_TIMEOUT",
    "APPROVED",
    "ASSIGNED",
]


class ScoreTerm(BaseModel):
    """One term of the penalty: points = weight * value (docs/workflow.md, section 6.15)."""

    name: Literal[
        "candidate_count",
        "consecutive_shift",
        "workload_imbalance",
        "projected_overtime",
        "candidate_source",
    ]
    value: int | float
    weight: int | float
    points: int | float


class CandidateScore(BaseModel):
    total: int | float
    terms: list[ScoreTerm]
    first_wave: bool


class CandidateView(BaseModel):
    candidate_item_id: int
    rank: int
    staff_id: int
    first_name: str
    last_name: str
    source: CandidateSource
    # null until an offer was created for this candidate
    outreach_status: OutreachStatus | None
    stage: CandidateStage
    # null for a plan created before PR E: its snapshot has no exact values
    score: CandidateScore | None


class CaseDetail(BaseModel):
    """GET /cases/{id}. `status` is the key the E2E test reads."""

    id: int
    status: CaseStatus
    # Every event of the case, by ID. One window can merge several
    event_ids: list[int]
    shift_id: int
    required_replacement_time: AppDatetime
    created_at: AppDatetime
    updated_at: AppDatetime
    # null until the ASSESSING step stored a gap
    gap: GapView | None
    # People this case already put on the roster. The case is still short of
    # max(gap.headcount_gap - assigned_count, 0) people
    assigned_count: int
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
    created_at: AppDatetime
