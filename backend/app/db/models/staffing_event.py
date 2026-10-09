from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import StrEnumText
from app.domain.enums import STAFF_EVENT_TYPES, EventStatus, EventType

# Alembic does not compare CHECK constraints, so a change to STAFF_EVENT_TYPES
# needs a hand-written migration that drops and recreates this one
_STAFF_EVENT_TYPES_SQL = ", ".join(
    f"'{event_type.value}'" for event_type in sorted(STAFF_EVENT_TYPES)
)


class StaffingEvent(Base):
    __tablename__ = "staffing_events"
    __table_args__ = (
        # Staff-group events require staff_id, demand-group events must leave it NULL
        CheckConstraint(
            f"(event_type IN ({_STAFF_EVENT_TYPES_SQL})) = (staff_id IS NOT NULL)",
            name="staff_id_matches_event_group",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_type: Mapped[EventType] = mapped_column(StrEnumText(EventType))
    shift_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shift.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    staff_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("staff.id"))
    # {} when there are no details
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[EventStatus] = mapped_column(StrEnumText(EventStatus))
