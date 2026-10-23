"""What the Demo control picks from: every ward, and the shifts of a day with their people
(round 6 PR EV6, docs/workflow.md 6.36.5)."""

from pydantic import BaseModel

from app.domain.enums import RosterStatus, ShiftType
from app.schemas.types import AppDatetime


class DemoWard(BaseModel):
    id: int
    name: str
    is_active: bool
    is_float_pool: bool


class DemoRosterPerson(BaseModel):
    staff_id: int
    first_name: str
    last_name: str
    status: RosterStatus
    checked_in: bool


class DemoShift(BaseModel):
    id: int
    ward_id: int
    shift_type: ShiftType
    start_at: AppDatetime
    end_at: AppDatetime
    # Every roster row of the shift, by staff ID: who can check in or report leave
    people: list[DemoRosterPerson]
