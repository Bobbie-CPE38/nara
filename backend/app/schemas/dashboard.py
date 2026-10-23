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


class WardCount(BaseModel):
    ward_id: int
    count: int


class WardOption(BaseModel):
    """A ward the user may pick on the Dashboard (round 6 PR EV6, 6.36.4)."""

    id: int
    name: str


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
    # Every case status in workflow order, zero counts included
    cases_by_status: list[CaseStatusCount]
    shortages: list[Shortage]
    # Approval requests still waiting for each ward's decision
    pending_approvals: list[WardCount]
    open_offers: OpenOffers
    recent_no_show: list[NoShowEvent]
    # null while LLM_ENABLED is false
    llm_usage: LlmUsage | None
