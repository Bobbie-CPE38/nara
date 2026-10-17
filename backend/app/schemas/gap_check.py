"""Answers of the read-only gap check routes (docs/workflow.md 6.31, 9.8, round 6 PR F1)."""

from pydantic import BaseModel

from app.domain.enums import RosterStatus
from app.schemas.case import GapIntervalView
from app.schemas.types import AppDatetime


class GapShiftSummary(BaseModel):
    """One item of GET /gap/shifts: a shift of the day with its gap measured now."""

    shift_id: int
    ward_id: int
    start_at: AppDatetime
    end_at: AppDatetime
    # required_staff of the shift's current requirement
    required_staff: int
    # People on the roster who cover the shift (ASSIGNED or COMPLETED), whole or part
    rostered_count: int
    # The worst slice from now on, as headcount_gap of GET /cases/{id}; display only
    headcount_gap: int
    # The shift's case that has not ended, if any
    case_id: int | None


class GapRosterEntry(BaseModel):
    roster_assignment_id: int
    staff_id: int
    name: str
    status: RosterStatus
    # Actual times of the row, else the shift times
    effective_start_at: AppDatetime
    effective_end_at: AppDatetime
    # A leave or NO_SHOW period of the person overlaps the shift
    on_leave: bool
    checked_in: bool


class GapShiftDetail(BaseModel):
    """GET /gap/shifts/{shift_id}: what `assess_shift()` measures now. Writes nothing."""

    shift_id: int
    ward_id: int
    start_at: AppDatetime
    end_at: AppDatetime
    evaluated_from: AppDatetime | None
    # Same shape as gap.intervals of GET /cases/{id}: every slice, short or not
    intervals: list[GapIntervalView]
    roster: list[GapRosterEntry]
    case_id: int | None
