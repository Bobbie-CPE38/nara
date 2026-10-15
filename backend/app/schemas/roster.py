"""Answers of GET /roster?shift_id= and GET /roster?staff_id= (docs/workflow.md, 9.3 and 9.5)."""

from pydantic import BaseModel

from app.domain.enums import (
    AssignmentType,
    CandidateSource,
    RosterStatus,
    ShiftType,
    StaffStatus,
)
from app.schemas.types import AppDatetime


class RosterShift(BaseModel):
    id: int
    ward_id: int
    ward_name: str
    shift_type: ShiftType
    start_at: AppDatetime
    end_at: AppDatetime
    # An inactive shift still answers with its rows
    is_active: bool


class RosterRow(BaseModel):
    """One ROSTER_ASSIGNMENT row with the person it belongs to.

    A row, not a person: the same staff member appears once per row they have
    on the shift. `id` and `status` are the assignment's own.
    """

    id: int
    status: RosterStatus
    assignment_type: AssignmentType
    # null for REGULAR rows
    candidate_source: CandidateSource | None
    actual_start_at: AppDatetime | None
    actual_end_at: AppDatetime | None
    transferred_from_assignment_id: int | None
    staff_id: int
    first_name: str
    last_name: str
    # Employment status. An INACTIVE person can still hold a row
    staff_status: StaffStatus
    role_id: int
    role_name: str
    # Differs from the shift's ward for staff who come from another ward
    home_ward_id: int
    home_ward_name: str
    # ASSIGNED, and a STAFF_UNAVAILABILITY period overlaps the effective interval
    # (an open end_at counts). Same overlap as the UNAVAILABLE hard rule
    is_unavailable: bool
    created_at: AppDatetime
    updated_at: AppDatetime


class ShiftRoster(BaseModel):
    shift: RosterShift
    # Every status, ordered by id. Empty for a shift without rows
    assignments: list[RosterRow]


class RosterStaff(BaseModel):
    id: int
    first_name: str
    last_name: str
    # Employment status. An INACTIVE person can still hold rows
    staff_status: StaffStatus
    role_id: int
    role_name: str
    home_ward_id: int
    home_ward_name: str


class StaffRosterRow(BaseModel):
    """One ROSTER_ASSIGNMENT row of the person with the shift it is on."""

    id: int
    status: RosterStatus
    assignment_type: AssignmentType
    # null for REGULAR rows
    candidate_source: CandidateSource | None
    actual_start_at: AppDatetime | None
    actual_end_at: AppDatetime | None
    transferred_from_assignment_id: int | None
    shift: RosterShift
    # Same meaning as RosterRow.is_unavailable
    is_unavailable: bool
    created_at: AppDatetime
    updated_at: AppDatetime


class StaffRoster(BaseModel):
    staff: RosterStaff
    # Every status, ordered by shift start, then row id. Empty for nobody's rows
    assignments: list[StaffRosterRow]
