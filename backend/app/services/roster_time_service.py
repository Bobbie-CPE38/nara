"""Shared effective endpoints for roster readers. No writes or clock access."""

from datetime import datetime

from sqlalchemy import ColumnElement, func

from app.db.models import RosterAssignment, Shift


def start_at() -> ColumnElement[datetime]:
    """Use with a query joining RosterAssignment to Shift."""
    return func.coalesce(RosterAssignment.actual_start_at, Shift.start_at)


def end_at() -> ColumnElement[datetime]:
    """Each endpoint falls back independently, matching the nullable schema."""
    return func.coalesce(RosterAssignment.actual_end_at, Shift.end_at)
