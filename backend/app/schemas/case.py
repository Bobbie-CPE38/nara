"""Answers of the case read routes (docs/workflow.md, section 9.3)."""

from typing import Any, Literal

from pydantic import BaseModel

from app.domain.enums import (
    ActorType,
    ApprovalSide,
    AuditAction,
    CandidateSource,
    CaseStatus,
    EntityType,
    EventType,
    ExplanationBlock,
    ExplanationViewStatus,
    OutreachStatus,
)
from app.schemas.case_summary import CaseSummaryView
from app.schemas.handover import HandoverView
from app.schemas.types import AppDatetime


class GapCount(BaseModel):
    """One role or skill of a gap. `id` is the role ID or the skill ID."""

    id: int
    name: str
    required_count: int
    current_count: int
    gap_count: int


class HeadcountCount(BaseModel):
    """Headcount of one time slice of a gap."""

    required_count: int
    current_count: int
    gap_count: int


class GapIntervalView(BaseModel):
    """One time slice [start_at, end_at) of a gap (round 4 PR T3, workflow.md 6.20)."""

    start_at: AppDatetime
    end_at: AppDatetime
    headcount: HeadcountCount
    roles: list[GapCount]
    skills: list[GapCount]


class GapView(BaseModel):
    id: int
    # The headcount target the gap was measured against, stored with the gap row
    effective_minimum: int
    # The worst slice of each dimension; display only, never for deciding
    headcount_gap: int
    computed_at: AppDatetime
    roles: list[GapCount]
    skills: list[GapCount]
    # Where the measured window starts; null for a gap written before round 4
    evaluated_from: AppDatetime | None
    # Every slice in time order, also those without a shortage. Empty for a gap
    # written before round 4, which is short for the whole shift
    intervals: list[GapIntervalView]


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


class SourceAssignmentView(BaseModel):
    """The roster row a candidate is moved out of when they take this shift."""

    assignment_id: int
    shift_id: int
    ward_id: int
    ward_name: str


class CandidateView(BaseModel):
    candidate_item_id: int
    rank: int
    staff_id: int
    first_name: str
    last_name: str
    source: CandidateSource
    # The candidate's home ward (docs/workflow.md, section 9.6)
    home_ward_id: int
    home_ward_name: str
    # null until an offer was created for this candidate
    outreach_status: OutreachStatus | None
    stage: CandidateStage
    # null for a plan created before PR E: its snapshot has no exact values
    score: CandidateScore | None
    # Both null = the candidate covers the whole shift (docs/workflow.md, section 6.20)
    cover_start_at: AppDatetime | None
    cover_end_at: AppDatetime | None
    # null = the candidate is not moved out of another shift
    source_assignment: SourceAssignmentView | None


class RankExplanationView(BaseModel):
    """The LLM explanation of the rank, made only when a user asks (round 6 PR E1).
    Never carries a failure reason, tokens or the payload."""

    status: ExplanationViewStatus
    # The next three are set only when READY (model_id is null for the fake provider)
    text: str | None
    provider: Literal["fake", "bedrock", "lambda"] | None
    model_id: str | None
    # True when POST /cases/{id}/explanation would queue the explanation now
    can_request: bool
    # null exactly when can_request is true
    request_blocked_reason: ExplanationBlock | None


class OverviewPerson(BaseModel):
    """Someone the case overview names: who left, who came, who decided (round 6 PR EV7)."""

    staff_id: int | None
    # "System" (or the component) when no person did it, e.g. auto-approval
    name: str
    role: str | None
    ward_name: str | None


class OverviewEvent(BaseModel):
    event_id: int
    event_type: EventType
    # The person the event is about (who is on leave, who did not come); None for a surge
    staff: OverviewPerson | None
    occurred_at: AppDatetime


class OverviewReplacement(BaseModel):
    staff: OverviewPerson
    # APPROVED (offer and approval), TRANSFERRED (moved from another ward's shift) or MANUAL
    how: Literal["APPROVED", "TRANSFERRED", "MANUAL"]
    at: AppDatetime


class OverviewDecision(BaseModel):
    """One human or automatic decision on the case, with its ward side for an approval."""

    kind: Literal[
        "APPROVED",
        "REJECTED",
        "AUTO_APPROVED",
        "APPROVAL_TIMEOUT",
        "MANUAL_ASSIGNMENT",
        "CLOSED_UNRESOLVED",
    ]
    by: OverviewPerson
    # The ward the decision speaks for: each side of a cross-ward move has its own
    ward_name: str | None
    side: ApprovalSide | None
    # The candidate the decision is about
    candidate: OverviewPerson | None
    reason: str | None
    at: AppDatetime


class OverviewOutcome(BaseModel):
    """Why the case stopped where it is: a handoff, a close, or a failure."""

    kind: Literal["MANUAL_HANDOFF", "CLOSED_UNRESOLVED", "FAILED"]
    # A ManualHandoffReason code, the words of whoever closed it, or the error type
    reason: str | None
    by: OverviewPerson | None
    at: AppDatetime


class CaseOverview(BaseModel):
    """The top of the case page: what happened, who came, who decided, why it stopped
    (round 6 PR EV7, docs/workflow.md 6.37.2). All of it is in the timeline too."""

    events: list[OverviewEvent]
    replacements: list[OverviewReplacement]
    decisions: list[OverviewDecision]
    outcome: OverviewOutcome | None


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
    # null when there is no plan or the latest plan has no candidates
    explanation: RankExplanationView | None
    # True when the latest plan's first wave comes from the max-coverage stages: no
    # group could cover every target (round 4 PR T4). False without a plan
    partial_plan: bool
    handovers: list[HandoverView]
    summary: CaseSummaryView | None
    overview: CaseOverview


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
