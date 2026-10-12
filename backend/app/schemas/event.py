from typing import Self

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.core.constants import MAX_BIGINT
from app.domain.enums import CaseStatus, EventStatus, EventType

# The count columns are PostgreSQL integer: a larger number would fail in the database
MAX_INTEGER = 2**31 - 1

# The detail fields each event type takes (docs/workflow.md, section 3.4)
_DETAIL_FIELDS: dict[EventType, frozenset[str]] = {
    EventType.STAFF_UNAVAILABLE: frozenset({"end_at"}),
    EventType.ASSIGNMENT_CANCELLED: frozenset({"staff_id", "reason"}),
    EventType.PATIENT_SURGE: frozenset({"patient_count"}),
    EventType.REQUIREMENT_CHANGED: frozenset({"roles", "skills"}),
}
_ALL_DETAIL_FIELDS = frozenset().union(*_DETAIL_FIELDS.values())


class RoleCount(BaseModel):
    role_id: int = Field(gt=0, le=MAX_BIGINT)
    required_count: int = Field(ge=0, le=MAX_INTEGER)


class SkillCount(BaseModel):
    skill_id: int = Field(gt=0, le=MAX_BIGINT)
    required_count: int = Field(ge=0, le=MAX_INTEGER)


class EventCreate(BaseModel):
    """Body of POST /events. The reporting staff member comes from X-Demo-User.

    Only the detail fields of the given event type may be sent.
    """

    event_type: EventType
    # SHIFT.id is a PostgreSQL bigint: a larger number would fail in the database
    shift_id: int = Field(gt=0, le=MAX_BIGINT)
    # STAFF_UNAVAILABLE: the return time the staff member gave. Omitted = until the shift ends
    end_at: AwareDatetime | None = None
    # ASSIGNMENT_CANCELLED: whose assignment is cancelled, and why
    staff_id: int | None = Field(default=None, gt=0, le=MAX_BIGINT)
    reason: str | None = None
    # PATIENT_SURGE: the new total of the shift, not a difference
    patient_count: int | None = Field(default=None, ge=0, le=MAX_INTEGER)
    # REQUIREMENT_CHANGED: new counts of roles and skills the requirement already has
    roles: list[RoleCount] | None = None
    skills: list[SkillCount] | None = None

    @model_validator(mode="after")
    def _details_fit_the_event_type(self) -> Self:
        allowed = _DETAIL_FIELDS[self.event_type]
        foreign = sorted(
            name for name in _ALL_DETAIL_FIELDS - allowed if getattr(self, name) is not None
        )
        if foreign:
            raise ValueError(f"{self.event_type.value} does not take {', '.join(foreign)}")
        if self.event_type is EventType.ASSIGNMENT_CANCELLED:
            if self.staff_id is None:
                raise ValueError("staff_id of the cancelled person is required")
            if self.reason is None or not self.reason.strip():
                raise ValueError("reason is required")
        if self.event_type is EventType.PATIENT_SURGE and self.patient_count is None:
            raise ValueError("patient_count is required")
        if self.event_type is EventType.REQUIREMENT_CHANGED:
            role_ids = [item.role_id for item in self.roles or []]
            skill_ids = [item.skill_id for item in self.skills or []]
            if not role_ids and not skill_ids:
                raise ValueError("At least one role or skill is required")
            if len(set(role_ids)) != len(role_ids) or len(set(skill_ids)) != len(skill_ids):
                raise ValueError("A role or skill may appear only once")
        return self


class EventResult(BaseModel):
    """Answer of POST /events and GET /events/{event_id} (docs/workflow.md, section 9.3)."""

    event_id: int
    event_status: EventStatus
    # Both null when the event has no case: IGNORED = there will be none,
    # RECEIVED = its merge window has not closed yet
    case_id: int | None
    case_status: CaseStatus | None
