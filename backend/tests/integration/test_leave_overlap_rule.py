"""One overlap rule for a leave and a shift, in Python and in SQL (round 3 PR R review).

The UNAVAILABLE hard rule uses context.leave_overlaps_shift(); GET /roster and the
overlap report of PATCH /unavailability use unavailability_service.
leave_overlaps_shift_sql(). Each boundary case must give the same answer in both,
with the SQL inputs given as Python values and as columns.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Shift, StaffUnavailability
from app.domain.constraints.codes import HardRuleCode
from app.domain.constraints.context import leave_overlaps_shift
from app.domain.enums import AvailabilityReason
from app.services import hard_rule_service
from app.services.unavailability_service import leave_overlaps_shift_sql

NIGHT_SHIFT = 1

# (leave start, leave end) relative to the shift start; the shift lasts 8 hours
CASES: list[tuple[timedelta, timedelta | None, bool]] = [
    (timedelta(hours=-1), timedelta(hours=1), True),
    (timedelta(hours=2), timedelta(hours=3), True),  # inside
    (timedelta(hours=-1), timedelta(hours=9), True),  # covers it
    (timedelta(hours=7, minutes=59), timedelta(hours=9), True),
    (timedelta(hours=-5), timedelta(seconds=1), True),
    (timedelta(hours=-5), None, True),  # no end yet
    (timedelta(hours=7), None, True),
    (timedelta(hours=8), timedelta(hours=9), False),  # starts as the shift ends
    (timedelta(hours=-5), timedelta(0), False),  # ends as the shift starts
    (timedelta(hours=8), None, False),
    (timedelta(hours=-5), timedelta(hours=-1), False),
]


def _night(db: Session) -> Shift:
    shift = db.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    return shift


@pytest.mark.parametrize(("start", "end", "expected"), CASES)
def test_python_and_sql_agree_on_every_boundary(
    seeded: Session, start: timedelta, end: timedelta | None, expected: bool
) -> None:
    night = _night(seeded)
    leave_start = night.start_at + start
    leave_end = None if end is None else night.start_at + end
    period = StaffUnavailability(
        staff_id=201,
        start_at=leave_start,
        end_at=leave_end,
        reason=AvailabilityReason.PLANNED_LEAVE,
    )
    seeded.add(period)
    seeded.flush()

    python = leave_overlaps_shift(leave_start, leave_end, night.start_at, night.end_at)
    sql_values = seeded.scalar(
        select(leave_overlaps_shift_sql(leave_start, leave_end, night.start_at, night.end_at))
    )
    # Leave columns against shift values: what GET /roster?shift_id= runs
    leave_columns = seeded.scalar(
        select(
            leave_overlaps_shift_sql(
                StaffUnavailability.start_at,
                StaffUnavailability.end_at,
                night.start_at,
                night.end_at,
            )
        ).where(StaffUnavailability.id == period.id)
    )
    # Leave values against shift columns: what the PATCH overlap report runs
    shift_columns = seeded.scalar(
        select(
            leave_overlaps_shift_sql(leave_start, leave_end, Shift.start_at, Shift.end_at)
        ).where(Shift.id == NIGHT_SHIFT)
    )

    assert (python, sql_values, leave_columns, shift_columns) == (expected,) * 4


def test_the_hard_rule_uses_the_shared_rule(seeded: Session) -> None:
    """A touching leave is not UNAVAILABLE for the Solver either."""
    night = _night(seeded)
    seeded.add(
        StaffUnavailability(
            staff_id=201,
            start_at=night.end_at,
            end_at=night.end_at + timedelta(hours=1),
            reason=AvailabilityReason.PLANNED_LEAVE,
        )
    )
    seeded.flush()

    touching = hard_rule_service.check_staff(seeded, shift=night, staff_ids=[201])[201]

    seeded.add(
        StaffUnavailability(
            staff_id=202,
            start_at=night.end_at - timedelta(seconds=1),
            end_at=None,
            reason=AvailabilityReason.PLANNED_LEAVE,
        )
    )
    seeded.flush()
    overlapping = hard_rule_service.check_staff(seeded, shift=night, staff_ids=[202])[202]

    assert HardRuleCode.UNAVAILABLE not in touching.result.failed_rules
    assert HardRuleCode.UNAVAILABLE in overlapping.result.failed_rules
