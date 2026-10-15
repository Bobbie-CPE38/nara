"""Shared effective endpoints for roster readers. No writes or clock access."""

from datetime import datetime

from sqlalchemy import ColumnElement, func

from app.db.models import RosterAssignment, Shift


def effective_interval(
    *,
    shift_start_at: datetime,
    shift_end_at: datetime,
    actual_start_at: datetime | None,
    actual_end_at: datetime | None,
) -> tuple[datetime, datetime]:
    """Validate writer endpoints after applying independent shift fallbacks.

    The database CHECK covers only two non-NULL actual endpoints. Writers of
    partial overrides must also use this check against the locked Shift times.
    """
    start = actual_start_at if actual_start_at is not None else shift_start_at
    end = actual_end_at if actual_end_at is not None else shift_end_at
    if start >= end:
        raise ValueError("The effective roster interval must have start before end")
    return start, end


def start_at() -> ColumnElement[datetime]:
    """Use with a query joining RosterAssignment to Shift."""
    return func.coalesce(RosterAssignment.actual_start_at, Shift.start_at)


def end_at() -> ColumnElement[datetime]:
    """Each endpoint falls back independently, matching the nullable schema."""
    return func.coalesce(RosterAssignment.actual_end_at, Shift.end_at)
