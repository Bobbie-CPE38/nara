"""KPI of one test run from the audit log of its case (round 6 PR EV5a, docs/workflow.md 6.35.4).

Every time is a number of seconds between two actions of the case, counted as the
time the tester really spent: system time between the two points minus every clock
advance that happened between them. The system time before that subtraction is kept
next to it (`*_system_s`). A value that did not happen in the run is None, never 0.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.enums import AuditAction

FILL_ACTIONS = (
    AuditAction.ASSIGNMENT_CREATED,
    AuditAction.ASSIGNMENT_TRANSFERRED,
    AuditAction.MANUAL_ASSIGNMENT_CREATED,
)

# KPI name, the action it starts at, the action it ends at (6.35.4)
INTERVALS: tuple[tuple[str, tuple[AuditAction, ...], tuple[AuditAction, ...]], ...] = (
    ("detect_s", (AuditAction.EVENT_RECEIVED,), (AuditAction.GAP_ASSESSED,)),
    ("shortlist_s", (AuditAction.EVENT_RECEIVED,), (AuditAction.SOLVER_EXECUTED,)),
    ("first_offer_s", (AuditAction.EVENT_RECEIVED,), (AuditAction.OFFER_SENT,)),
    ("first_accept_s", (AuditAction.OFFER_SENT,), (AuditAction.OFFER_ACCEPTED,)),
    ("approval_s", (AuditAction.APPROVAL_REQUESTED,), (AuditAction.APPROVAL_APPROVED,)),
    ("time_to_fill_s", (AuditAction.EVENT_RECEIVED,), FILL_ACTIONS),
)
# Every column of a finished run's KPI, in CSV order
KPI_COLUMNS = (
    *(name for name, _, _ in INTERVALS),
    *(name.removesuffix("_s") + "_system_s" for name, _, _ in INTERVALS),
    "filled_before_shift_start",
    "offers_sent",
    "candidates_skipped_by_rules",
    "from_other_ward",
)


@dataclass(frozen=True)
class Row:
    action: AuditAction
    at: datetime
    payload: dict[str, Any]


@dataclass(frozen=True)
class Advance:
    """One TEST_RUN_CLOCK_ADVANCED row: system time just before and just after the move."""

    before: datetime
    after: datetime
    seconds: float


def _first(rows: Sequence[Row], actions: tuple[AuditAction, ...]) -> Row | None:
    return next((row for row in rows if row.action in actions), None)


def advanced_between(advances: Sequence[Advance], start: datetime, end: datetime) -> float:
    """Seconds the clock was moved inside [start, end]. A move that started before the
    start is outside the interval: the start itself was written after it."""
    return sum(move.seconds for move in advances if start <= move.before and move.after <= end)


def compute(
    rows: Sequence[Row],
    advances: Sequence[Advance],
    *,
    required_replacement_time: datetime | None,
    skipped_by_plan: int,
    filled_from_other_ward: bool | None,
) -> dict[str, Any]:
    """The KPI of one run. `rows` are the audit rows of the case and of its events in time
    order; `skipped_by_plan` counts the people the first plan left out because of a rule."""
    ordered = sorted(rows, key=lambda row: row.at)
    kpi: dict[str, Any] = {}
    for name, starts, ends in INTERVALS:
        start = _first(ordered, starts)
        end = _first([row for row in ordered if start is not None and row.at >= start.at], ends)
        system_name = name.removesuffix("_s") + "_system_s"
        if start is None or end is None:
            kpi[name] = kpi[system_name] = None
            continue
        system = (end.at - start.at).total_seconds()
        kpi[system_name] = system
        kpi[name] = system - advanced_between(advances, start.at, end.at)
    fill = _first(ordered, FILL_ACTIONS)
    kpi["filled_before_shift_start"] = (
        None
        if fill is None or required_replacement_time is None
        else fill.at <= required_replacement_time
    )
    kpi["offers_sent"] = sum(row.action == AuditAction.OFFER_SENT for row in ordered)
    kpi["candidates_skipped_by_rules"] = skipped_by_plan + sum(
        row.action == AuditAction.SAFETY_FAILED for row in ordered
    )
    kpi["from_other_ward"] = None if fill is None else filled_from_other_ward
    return kpi
