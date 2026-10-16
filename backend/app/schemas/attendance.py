"""POST /me/attendance/check-in and POST /demo/attendance/check-in (docs/workflow.md, 9.3)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import MAX_BIGINT
from app.schemas.types import AppDatetime

BigintId = Annotated[int, Field(ge=1, le=MAX_BIGINT)]


class MyCheckIn(BaseModel):
    """Only the shift: the person is the X-Demo-User header, so a staff_id is a 422."""

    model_config = ConfigDict(extra="forbid")
    shift_id: BigintId


class SimulatedCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_id: BigintId
    shift_id: BigintId


class CheckInResponse(BaseModel):
    attendance_id: int
    shift_id: int
    check_in_at: AppDatetime
    on_time: bool
    deadline: AppDatetime
