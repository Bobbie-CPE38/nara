"""Answers of the routes that close what is due (docs/workflow.md, sections 3.8 and 9.2)."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import CaseStatus
from app.schemas.types import AppDatetime
from app.services.job_service import DueWork

# One week. The demo only needs minutes; the bound keeps a typo from moving the
# clock by years
MAX_ADVANCE_SECONDS = 7 * 24 * 60 * 60


class ClosedWindowView(BaseModel):
    """One merge window that was closed. No case when its events were IGNORED."""

    shift_id: int
    event_ids: list[int]
    case_id: int | None
    case_status: CaseStatus | None


def _views(work: DueWork) -> list[ClosedWindowView]:
    return [
        ClosedWindowView(
            shift_id=window.shift_id,
            event_ids=list(window.event_ids),
            case_id=window.case_id,
            case_status=window.case_status,
        )
        for window in work.closed_windows
    ]


class DueWorkResult(BaseModel):
    """Answer of POST /internal/merge-windows/close-due."""

    closed_windows: list[ClosedWindowView]

    @classmethod
    def of(cls, work: DueWork) -> "DueWorkResult":
        return cls(closed_windows=_views(work))


class ClockAdvance(BaseModel):
    """Body of POST /demo/clock/advance."""

    seconds: int = Field(gt=0, le=MAX_ADVANCE_SECONDS)


class ClockAdvanceResult(BaseModel):
    """Answer of POST /demo/clock/advance: the new demo time and what it made due."""

    clock: AppDatetime
    closed_windows: list[ClosedWindowView]
    # Offers the new time set to TIMEOUT, and waiting cases the sweep moved on
    # (section 6.9). Both by ID, so the demo shows why a case left its wait
    timed_out_outreach_ids: list[int]
    recovered_case_ids: list[int]

    @classmethod
    def of(cls, now: datetime, work: DueWork) -> "ClockAdvanceResult":
        return cls(
            clock=now,
            closed_windows=_views(work),
            timed_out_outreach_ids=sorted(work.timed_out_outreach_ids),
            recovered_case_ids=sorted(work.recovered_case_ids),
        )
