"""The pure time rules of check-in (docs/workflow.md, section 6.24)."""

from datetime import datetime, timedelta

import pytest

from app.core import clock
from app.core.constants import CHECK_IN_EARLIEST_SECONDS, NO_SHOW_GRACE_SECONDS
from app.db.models import RosterAssignment, Shift
from app.domain.enums import AssignmentType
from app.services import attendance_service as rules

START = datetime(2026, 10, 9, 23, 0, tzinfo=clock.APP_TIMEZONE)
END = START + timedelta(hours=8)
SHIFT = Shift(start_at=START, end_at=END)


def row(
    kind: AssignmentType = AssignmentType.REGULAR,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    created: datetime = START - timedelta(days=1),
) -> RosterAssignment:
    return RosterAssignment(
        assignment_type=kind, actual_start_at=start, actual_end_at=end, created_at=created
    )


def test_regular_arrival_is_the_shift_start_whatever_created_at_says() -> None:
    assert rules.required_arrival_at(row(created=START + timedelta(hours=3)), SHIFT) == START


def test_regular_arrival_uses_actual_start_when_set() -> None:
    late = START + timedelta(hours=2)
    assert rules.required_arrival_at(row(start=late), SHIFT) == late


@pytest.mark.parametrize(
    ("created_hours", "expected_hours"), [(-5, 0), (0, 0), (2, 2)], ids=["before", "equal", "after"]
)
def test_replacement_arrival_is_the_later_of_start_and_created_at(
    created_hours: int, expected_hours: int
) -> None:
    created = START + timedelta(hours=created_hours)
    arrival = rules.required_arrival_at(row(AssignmentType.REPLACEMENT, created=created), SHIFT)
    assert arrival == START + timedelta(hours=expected_hours)


def test_replacement_compares_created_at_with_actual_start() -> None:
    late = START + timedelta(hours=2)
    replacement = row(AssignmentType.REPLACEMENT, start=late, created=START + timedelta(hours=1))
    assert rules.required_arrival_at(replacement, SHIFT) == late


def test_deadline_is_arrival_plus_the_grace_period() -> None:
    assert rules.deadline_at(row(), SHIFT) == START + timedelta(seconds=NO_SHOW_GRACE_SECONDS)


def test_effective_end_falls_back_to_the_shift_end() -> None:
    assert rules.effective_end_at(row(), SHIFT) == END
    early = START + timedelta(hours=3)
    assert rules.effective_end_at(row(end=early), SHIFT) == early


def test_window_is_closed_at_the_lower_bound_and_open_at_the_upper() -> None:
    earliest = START - timedelta(seconds=CHECK_IN_EARLIEST_SECONDS)
    one = timedelta(seconds=1)
    assert not rules.accepts_check_in(row(), SHIFT, earliest - one)
    assert rules.accepts_check_in(row(), SHIFT, earliest)
    assert rules.accepts_check_in(row(), SHIFT, END - one)
    assert not rules.accepts_check_in(row(), SHIFT, END)


def test_window_closes_at_the_actual_end() -> None:
    early = START + timedelta(hours=3)
    assert rules.accepts_check_in(row(end=early), SHIFT, early - timedelta(seconds=1))
    assert not rules.accepts_check_in(row(end=early), SHIFT, early)


def test_on_time_includes_the_deadline_itself() -> None:
    deadline = rules.deadline_at(row(), SHIFT)
    assert rules.is_on_time(row(), SHIFT, deadline)
    assert not rules.is_on_time(row(), SHIFT, deadline + timedelta(seconds=1))


@pytest.mark.parametrize(
    "roster,opening,closing",
    [
        (row(AssignmentType.REPLACEMENT), "09/10/2026 22:00:00", "10/10/2026 07:00:00"),
        (
            row(AssignmentType.REPLACEMENT, created=START + timedelta(hours=2, seconds=25)),
            "10/10/2026 00:00:25",
            "10/10/2026 07:00:00",
        ),
        (
            row(
                AssignmentType.REPLACEMENT,
                start=START + timedelta(hours=3),
                end=START + timedelta(hours=5),
            ),
            "10/10/2026 01:00:00",
            "10/10/2026 04:00:00",
        ),
    ],
)
def test_line_instructions_use_exact_checkin_bounds(roster, opening, closing):
    from app.services.line_delivery_service import _check_in_instructions

    message = _check_in_instructions(roster, SHIFT)
    assert f"กดได้ตั้งแต่ {opening} น." in message
    assert f"ถึงก่อน {closing} น." in message
    assert len(message) <= 160  # LINE buttons template, without title/image
    assert rules.accepts_check_in(roster, SHIFT, rules.earliest_check_in_at(roster, SHIFT))
    assert not rules.accepts_check_in(roster, SHIFT, rules.effective_end_at(roster, SHIFT))
