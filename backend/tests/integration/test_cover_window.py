"""The cover window and the source assignment in hard_rule_service (round 4, PR T1).

The "Y example": staff 201 works another shift 23:00-07:00, then is moved out of it at
01:00 to cover the last six hours of the night shift. The kept two hours and the cover
are one eight-hour duty, so the rest rule must not reject them.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.db.models import CandidateItem, RosterAssignment, Shift
from app.domain.constraints.codes import HardRuleCode
from app.domain.constraints.context import ShiftSlot
from app.domain.enums import (
    AssignmentType,
    OutreachStatus,
    RosterStatus,
    ShiftType,
)
from app.services import hard_rule_service, safety_service
from app.services.hard_rule_service import Cover
from tests.integration.case_rows import (
    NIGHT_SHIFT,
    make_case,
    make_plan,
    offer,
)

STAFF = 201


def _night(db: Session) -> Shift:
    shift = db.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    return shift


def _shift(db: Session, start_at: datetime, end_at: datetime) -> Shift:
    shift = Shift(
        ward_id=1,
        patient_count=2,
        start_at=start_at,
        end_at=end_at,
        shift_type=ShiftType.NIGHT,
        is_active=True,
    )
    db.add(shift)
    db.flush()
    return shift


def _assign(
    db: Session, shift: Shift, staff_id: int = STAFF, status: RosterStatus = RosterStatus.ASSIGNED
) -> RosterAssignment:
    row = RosterAssignment(
        staff_id=staff_id,
        shift_id=shift.id,
        status=status,
        assignment_type=AssignmentType.REGULAR,
    )
    db.add(row)
    db.flush()
    return row


def _y_example(db: Session) -> tuple[Shift, RosterAssignment, Cover]:
    """Source shift with the night shift's times, and the cover that starts two hours in."""
    night = _night(db)
    source = _shift(db, night.start_at, night.end_at)
    row = _assign(db, source)
    cover_start = night.start_at + timedelta(hours=2)
    return night, row, Cover(cover_start, night.end_at, row.id)


def _failed(check: hard_rule_service.CandidateCheck) -> set[HardRuleCode]:
    return set(check.result.failed_rules)


def _item(db: Session, cover: Cover, staff_id: int = STAFF) -> CandidateItem:
    case = make_case(db)
    item = make_plan(db, case, (staff_id,))[staff_id]
    item.cover_start_at = cover.start_at
    item.cover_end_at = cover.end_at
    item.source_assignment_id = cover.source_assignment_id
    db.flush()
    return item


# --------------------------------------------------------------------------- #
# Cover value
# --------------------------------------------------------------------------- #
def test_a_cover_needs_both_ends_or_neither(seeded: Session) -> None:
    night = _night(seeded)

    with pytest.raises(ValueError):
        Cover(night.start_at, None, None)
    with pytest.raises(ValueError):
        Cover(None, night.end_at, None)
    assert Cover(None, None, None) == hard_rule_service.FULL_SHIFT


# --------------------------------------------------------------------------- #
# NULL cover changes nothing; planning and Safety agree
# --------------------------------------------------------------------------- #
def test_a_null_cover_item_is_checked_like_a_plain_candidate(seeded: Session) -> None:
    night = _night(seeded)
    case = make_case(seeded)
    items = make_plan(seeded, case, (201, 202, 203))

    by_item = hard_rule_service.check_items(seeded, shift=night, items=list(items.values()))
    by_staff = hard_rule_service.check_staff(seeded, shift=night, staff_ids=[201, 202, 203])

    for staff_id, item in items.items():
        assert by_item[item.id].context == by_staff[staff_id].context
        assert by_item[item.id].result == by_staff[staff_id].result


def test_planning_and_safety_build_the_same_context(seeded: Session) -> None:
    night, row, cover = _y_example(seeded)
    item = _item(seeded, cover)

    planned = hard_rule_service.check_staff(
        seeded, shift=night, staff_ids=[STAFF], covers={STAFF: cover}
    )[STAFF]
    stored = hard_rule_service.check_items(seeded, shift=night, items=[item])[item.id]

    assert planned.context == stored.context
    assert planned.result == stored.result
    assert planned.context.linked_duty is not None


# --------------------------------------------------------------------------- #
# The Y example
# --------------------------------------------------------------------------- #
def test_the_y_example_passes_as_one_eight_hour_duty(seeded: Session) -> None:
    night, row, cover = _y_example(seeded)

    check = hard_rule_service.check_staff(
        seeded, shift=night, staff_ids=[STAFF], covers={STAFF: cover}
    )[STAFF]

    assert check.result.failed_rules == ()
    assert check.result.details["daily_hours"] == 8
    assert check.result.details["projected_consecutive_shifts"] == 1
    assert check.context.proposed_shift.start_at == cover.start_at
    linked = check.context.linked_duty
    assert linked is not None
    assert (linked.start_at, linked.end_at) == (night.start_at, cover.start_at)


def test_the_same_cover_without_the_source_assignment_conflicts(seeded: Session) -> None:
    night, row, cover = _y_example(seeded)
    without_source = Cover(cover.start_at, cover.end_at, None)

    check = hard_rule_service.check_staff(
        seeded, shift=night, staff_ids=[STAFF], covers={STAFF: without_source}
    )[STAFF]

    assert HardRuleCode.SHIFT_CONFLICT in _failed(check)
    assert check.context.linked_duty is None


def test_a_whole_shift_move_drops_the_source_row(seeded: Session) -> None:
    night = _night(seeded)
    source = _shift(seeded, night.start_at, night.end_at)
    row = _assign(seeded, source)

    plain = hard_rule_service.check_staff(seeded, shift=night, staff_ids=[STAFF])[STAFF]
    moved = hard_rule_service.check_staff(
        seeded, shift=night, staff_ids=[STAFF], covers={STAFF: Cover(None, None, row.id)}
    )[STAFF]

    assert HardRuleCode.SHIFT_CONFLICT in _failed(plain)
    assert moved.result.failed_rules == ()
    assert moved.context.linked_duty is None
    assert all(entry.shift.shift_id != source.id for entry in moved.context.roster)


def test_a_gap_before_the_cover_gives_a_cut_without_a_link(seeded: Session) -> None:
    night = _night(seeded)
    # The source ends at 03:00 but the cover starts at 05:00: two duties, no link
    source = _shift(seeded, night.start_at, night.start_at + timedelta(hours=4))
    row = _assign(seeded, source)
    cover = Cover(night.start_at + timedelta(hours=6), night.end_at, row.id)

    check = hard_rule_service.check_staff(
        seeded, shift=night, staff_ids=[STAFF], covers={STAFF: cover}
    )[STAFF]

    assert check.context.linked_duty is None
    kept = [e for e in check.context.roster if e.shift.shift_id == source.id]
    assert [(e.shift.start_at, e.shift.end_at) for e in kept] == [
        (night.start_at, night.start_at + timedelta(hours=4))
    ]


def test_a_source_that_only_touches_the_cover_is_not_a_move(seeded: Session) -> None:
    night = _night(seeded)
    # Ends exactly when the cover starts: nothing is given up, so no linked duty
    source = _shift(seeded, night.start_at - timedelta(hours=8), night.start_at)
    row = _assign(seeded, source)
    touching = Cover(None, None, row.id)

    plain = hard_rule_service.check_staff(seeded, shift=night, staff_ids=[STAFF])[STAFF]
    check = hard_rule_service.check_staff(
        seeded, shift=night, staff_ids=[STAFF], covers={STAFF: touching}
    )[STAFF]

    assert HardRuleCode.INSUFFICIENT_REST in _failed(check)
    assert check.context.linked_duty is None
    assert _failed(check) == _failed(plain)
    assert [e.shift for e in check.context.roster if e.shift.shift_id == source.id] == [
        ShiftSlot(source.id, source.start_at, source.end_at)
    ]


def test_a_source_after_the_cover_is_not_a_move(seeded: Session) -> None:
    night = _night(seeded)
    # Starts two hours after the cover ends: the two do not overlap, so no move
    source = _shift(seeded, night.end_at + timedelta(hours=2), night.end_at + timedelta(hours=10))
    row = _assign(seeded, source)

    plain = hard_rule_service.check_staff(seeded, shift=night, staff_ids=[STAFF])[STAFF]
    check = hard_rule_service.check_staff(
        seeded, shift=night, staff_ids=[STAFF], covers={STAFF: Cover(None, None, row.id)}
    )[STAFF]

    assert HardRuleCode.INSUFFICIENT_REST in _failed(check)
    assert _failed(check) == _failed(plain)
    assert check.context.linked_duty is None
    assert [e.shift for e in check.context.roster if e.shift.shift_id == source.id] == [
        ShiftSlot(source.id, source.start_at, source.end_at)
    ]


def test_a_move_across_sunday_midnight_is_one_duty_of_the_day_it_starts(
    seeded: Session,
) -> None:
    night = _night(seeded)
    # Sunday 20:00 to Monday 04:00 in Asia/Bangkok; the cover starts at Monday 00:00
    night.start_at = datetime(2026, 10, 11, 13, 0, tzinfo=UTC)
    night.end_at = datetime(2026, 10, 11, 21, 0, tzinfo=UTC)
    source = _shift(seeded, night.start_at, night.end_at)
    row = _assign(seeded, source)
    cover = Cover(datetime(2026, 10, 11, 17, 0, tzinfo=UTC), night.end_at, row.id)

    check = hard_rule_service.check_staff(
        seeded, shift=night, staff_ids=[STAFF], covers={STAFF: cover}
    )[STAFF]

    assert check.result.failed_rules == ()
    assert check.result.details["daily_hours"] == 8
    assert check.result.details["projected_consecutive_shifts"] == 1
    linked = check.context.linked_duty
    assert linked is not None
    assert (linked.start_at, linked.end_at) == (night.start_at, cover.start_at)


# --------------------------------------------------------------------------- #
# Bad or stale source assignments
# --------------------------------------------------------------------------- #
def test_a_cancelled_source_row_changes_nothing_and_links_nothing(seeded: Session) -> None:
    night, row, cover = _y_example(seeded)
    row.status = RosterStatus.CANCELLED
    seeded.flush()

    check = hard_rule_service.check_staff(
        seeded, shift=night, staff_ids=[STAFF], covers={STAFF: cover}
    )[STAFF]

    assert check.context.linked_duty is None
    assert HardRuleCode.SHIFT_CONFLICT not in _failed(check)


def test_another_staff_members_source_row_is_refused(seeded: Session) -> None:
    night = _night(seeded)
    source = _shift(seeded, night.start_at, night.end_at)
    other = _assign(seeded, source, staff_id=202)
    cover = Cover(night.start_at + timedelta(hours=2), night.end_at, other.id)

    with pytest.raises(ValueError):
        hard_rule_service.check_staff(seeded, shift=night, staff_ids=[STAFF], covers={STAFF: cover})


def test_an_unknown_source_row_is_refused(seeded: Session) -> None:
    night = _night(seeded)

    with pytest.raises(LookupError):
        hard_rule_service.check_staff(
            seeded, shift=night, staff_ids=[STAFF], covers={STAFF: Cover(None, None, 999_999)}
        )


def test_a_source_row_on_the_proposed_shift_is_refused(seeded: Session) -> None:
    night = _night(seeded)
    own = _assign(seeded, night)

    with pytest.raises(ValueError):
        hard_rule_service.check_staff(
            seeded, shift=night, staff_ids=[STAFF], covers={STAFF: Cover(None, None, own.id)}
        )


def test_a_source_row_outside_the_roster_window_is_refused(seeded: Session) -> None:
    night = _night(seeded)
    far = _shift(seeded, night.start_at + timedelta(days=90), night.end_at + timedelta(days=90))
    row = _assign(seeded, far)

    with pytest.raises(ValueError):
        hard_rule_service.check_staff(
            seeded, shift=night, staff_ids=[STAFF], covers={STAFF: Cover(None, None, row.id)}
        )


@pytest.mark.parametrize(
    ("start_offset", "end_offset"),
    [(-1, 4), (2, 9), (4, 4), (5, 3)],
)
def test_a_cover_outside_the_shift_is_refused(
    seeded: Session, start_offset: int, end_offset: int
) -> None:
    night = _night(seeded)
    cover = Cover(
        night.start_at + timedelta(hours=start_offset),
        night.start_at + timedelta(hours=end_offset),
        None,
    )

    with pytest.raises(ValueError):
        hard_rule_service.check_staff(seeded, shift=night, staff_ids=[STAFF], covers={STAFF: cover})


# --------------------------------------------------------------------------- #
# Back-to-back shifts without a move are still rejected
# --------------------------------------------------------------------------- #
def test_a_back_to_back_shift_without_a_source_assignment_still_fails_rest(
    seeded: Session,
) -> None:
    night = _night(seeded)
    before = _shift(seeded, night.start_at - timedelta(hours=8), night.start_at)
    _assign(seeded, before)

    check = hard_rule_service.check_staff(seeded, shift=night, staff_ids=[STAFF])[STAFF]

    assert HardRuleCode.INSUFFICIENT_REST in _failed(check)


# --------------------------------------------------------------------------- #
# Read-only
# --------------------------------------------------------------------------- #
def test_checking_a_cover_is_read_only(production_seeded: Session) -> None:
    db = production_seeded
    night, row, cover = _y_example(db)
    with (
        patch.object(db, "flush", side_effect=AssertionError("read flushed")),
        patch.object(db, "commit", side_effect=AssertionError("read committed")),
    ):
        hard_rule_service.check_staff(db, shift=night, staff_ids=[STAFF], covers={STAFF: cover})


# --------------------------------------------------------------------------- #
# Safety reads the cover from the item
# --------------------------------------------------------------------------- #
def test_safety_passes_an_accepted_cover_with_a_source_assignment(seeded: Session) -> None:
    night, row, cover = _y_example(seeded)
    case = make_case(seeded)
    item = make_plan(seeded, case, (STAFF,))[STAFF]
    item.cover_start_at = cover.start_at
    item.cover_end_at = cover.end_at
    item.source_assignment_id = row.id
    seeded.flush()
    outreach = offer(seeded, case, item, OutreachStatus.ACCEPTED)

    result = safety_service.validate_accepted_candidate(seeded, case, outreach_id=outreach.id)

    assert result.validation.is_passed is True
    assert result.validation.validation_snapshot["failed_rules"] == []
    details = result.validation.validation_snapshot["details"]
    assert details["daily_hours"] == 8
    assert details["projected_consecutive_shifts"] == 1
