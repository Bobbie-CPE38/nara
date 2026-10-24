"""Answer of GET /dashboard (docs/workflow.md 6.31, 9.8, round 6 PR F1)."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.domain.enums import CaseStatus
from app.schemas.types import AppDatetime


class DashboardModes(BaseModel):
    """What is real in this demo: LINE simulation or real, LLM fake or Bedrock."""

    line_mode: Literal["simulation", "real"]
    llm_provider: Literal["fake", "bedrock", "lambda"]
    llm_enabled: bool


class CaseStatusCount(BaseModel):
    status: CaseStatus
    count: int


class NamedGap(BaseModel):
    name: str
    gap_count: int


class Shortage(BaseModel):
    """A shift of a visible ward that is short now (the worst slice from now on)."""

    shift_id: int
    ward_id: int
    start_at: AppDatetime
    end_at: AppDatetime
    headcount_gap: int
    # Only the roles and skills that are short
    role_gaps: list[NamedGap]
    skill_gaps: list[NamedGap]
    case_id: int | None
    # Running at `now`: listed before the shifts that start later (round 6 PR EV8)
    in_progress: bool


class WardShortage(BaseModel):
    """One bar of the Dashboard's chart: what a ward still misses in the window (EV8)."""

    ward_id: int
    # Headcount positions over the ward's short shifts: someone missing from two shifts
    # counts twice, so this is not a number of people
    missing_positions: int
    short_shifts: int


class Approver(BaseModel):
    staff_id: int
    name: str


class PendingApprovalCount(BaseModel):
    """Requests still waiting for one ward's decision, and who may decide them now (EV8).

    A ward's requests split in two rows when the Supervisor may decide some of them
    already (`supervisor_from` passed) and not the others."""

    ward_id: int
    count: int
    # The ward's active head nurses, who may decide at any time
    head_nurses: list[Approver]
    # True once the Supervisor may decide them too (docs/workflow.md 6.21)
    supervisor: bool


class DashboardSummary(BaseModel):
    """The four cards at the top of the Dashboard (round 6 PR EV8)."""

    # Shifts running now or starting within window_hours that are short
    short_shifts: int
    # Their headcount positions still missing, added over the shifts (not people)
    missing_positions: int
    # Approval requests waiting for a decision of one of the wards shown
    pending_approvals: int
    # Cases waiting in MANUAL_HANDOFF for a person to staff or close them
    handoff_cases: int


class WardOption(BaseModel):
    """A ward the user may pick on the Dashboard (round 6 PR EV6, 6.36.4)."""

    id: int
    name: str
    # False for a paused ward, which only a Supervisor is offered (review of #145)
    is_active: bool = True


class OpenOffers(BaseModel):
    count: int


class NoShowEvent(BaseModel):
    event_id: int
    shift_id: int
    staff_id: int
    # When the NO_SHOW job wrote the event (STAFFING_EVENTS.occurred_at)
    created_at: AppDatetime


class LlmUsage(BaseModel):
    """Today's DEMO attempts against the daily cap and this month's cost of every type."""

    # The quota day in LLM_QUOTA_TIMEZONE, by real time like the counter itself
    date: date
    used: int
    cap: int
    # Known cost of every work type started this month, trial included
    month_cost_usd: Decimal
    # Attempts of this month whose cost is unknown (no usage or no configured price),
    # so month_cost_usd may be lower than the real bill
    month_calls_without_cost: int
    budget_usd: Decimal


class Dashboard(BaseModel):
    now: AppDatetime
    modes: DashboardModes
    # The wards the numbers below cover: own ward, or every active ward for a Supervisor;
    # only the ward asked for with ?ward_id= (round 6 PR EV6, 6.36.4)
    wards: list[int]
    # Every ward the user may see, by name, for the ward filter (6.36.4)
    ward_options: list[WardOption]
    # How far ahead the shortages look, from `now` (DASHBOARD_SHORTAGE_WINDOW_HOURS)
    window_hours: int
    # True when the wards shown hold the demo's simulated people (round 6 PR EV8)
    demo_data: bool
    summary: DashboardSummary
    # Every case status in workflow order, zero counts included
    cases_by_status: list[CaseStatusCount]
    # In progress first, then by start; at most DASHBOARD_MAX_SHORTAGES
    shortages: list[Shortage]
    # Every ward with a short shift in the window, the most missing first
    shortage_by_ward: list[WardShortage]
    # Approval requests still waiting for each ward's decision, and who may decide
    pending_approvals: list[PendingApprovalCount]
    open_offers: OpenOffers
    recent_no_show: list[NoShowEvent]
    # null while LLM_ENABLED is false
    llm_usage: LlmUsage | None
