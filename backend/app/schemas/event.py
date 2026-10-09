from pydantic import AwareDatetime, BaseModel, Field

from app.core.constants import MAX_BIGINT
from app.domain.enums import CaseStatus, EventStatus, EventType


class EventCreate(BaseModel):
    """Body of POST /events. The acting staff member comes from X-Demo-User."""

    event_type: EventType
    # SHIFT.id is a PostgreSQL bigint: a larger number would fail in the database
    shift_id: int = Field(gt=0, le=MAX_BIGINT)
    # Return time the staff member gave. Omitted = until the shift ends
    end_at: AwareDatetime | None = None


class EventResult(BaseModel):
    """Answer of POST /events (docs/workflow.md, section 9.3)."""

    event_id: int
    event_status: EventStatus
    # Both null when the event was IGNORED: no gap, so no case
    case_id: int | None
    case_status: CaseStatus | None
