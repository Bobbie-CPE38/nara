"""What the Demo control picks from: every ward, and the shifts of a day with their people
(round 6 PR EV6, docs/workflow.md 6.36.5)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import CandidateResponse, RosterStatus, ShiftType
from app.schemas.outreach import OfferView
from app.schemas.types import MAX_BIGINT, AppDatetime


class DemoWard(BaseModel):
    id: int
    name: str
    is_active: bool
    is_float_pool: bool
    # The ward's first ACTIVE head nurse, who reports a patient surge from the Demo
    # control (round 6 PR EV7, 6.37.8); None when the ward has none
    head_nurse_id: int | None = None


class DemoOffer(OfferView):
    """An offer still open for an answer, with whom it is for (round 6 PR EV7, 6.37.8)."""

    first_name: str
    last_name: str


class DemoOfferAnswer(BaseModel):
    """Body of POST /demo/offers/{outreach_id}/response: the candidate's answer."""

    model_config = ConfigDict(extra="forbid")
    response: CandidateResponse


OutreachId = Annotated[int, Field(ge=1, le=MAX_BIGINT)]


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
