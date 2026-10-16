"""Gap time slices stored, read back and used to close a case (round 4 PR T3).

The seeded night shift runs 23:00 to 07:00 with RNs 101 to 105, and needs
5 RNs and 2 ICU nurses. The frozen clock starts at 21:00 (DEMO_NOW).
"""

import importlib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core import clock
from app.db.models import (
    RosterAssignment,
    Shift,
    StaffingGap,
    StaffingGapInterval,
    StaffingGapRoleInterval,
    StaffingGapSkillInterval,
)
from app.domain.enums import COVERING_ROSTER_STATUSES, RosterStatus
from app.domain.staffing.gap_calculator import GapResult, calculate_gap
from app.main import app
from app.services import case_facts_service, gap_service, policy_service, requirement_service
from app.services.requirement_service import RequirementNotFoundError
from tests.integration.case_rows import (
    NIGHT_SHIFT,
    approval,
    cancel_roster,
    make_case,
    record_gap,
    replacement,
    short_case,
)
from tests.integration.conftest import DEMO_NOW

RN, ICU = 1, 1
NIGHT_START = DEMO_NOW + timedelta(hours=2)
NIGHT_END = DEMO_NOW + timedelta(hours=10)


def _night(db: Session) -> Shift:
    shift = db.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    return shift


def _row(db: Session, staff_id: int) -> RosterAssignment:
    return db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == NIGHT_SHIFT
        )
    ).one()


def _slices(db: Session) -> list[tuple[object, object, int, int]]:
    result = gap_service.assess_shift(db, _night(db)).result
    return [
        (i.start_at, i.end_at, i.headcount.current_count, i.headcount.gap_count)
        for i in result.intervals
    ]


def test_a_gap_before_the_shift_is_measured_from_the_shift_start(seeded: Session) -> None:
    cancel_roster(seeded, 105)

    result = gap_service.assess_shift(seeded, _night(seeded)).result

    assert result.evaluated_from == NIGHT_START
    assert _slices(seeded) == [(NIGHT_START, NIGHT_END, 4, 1)]
    assert result.headcount_gap == 1


def test_a_started_shift_is_measured_from_now(seeded: Session) -> None:
    clock.set_time(NIGHT_START + timedelta(hours=3))
    cancel_roster(seeded, 105)

    result = gap_service.assess_shift(seeded, _night(seeded)).result

    assert result.evaluated_from == NIGHT_START + timedelta(hours=3)
    assert _slices(seeded) == [(NIGHT_START + timedelta(hours=3), NIGHT_END, 4, 1)]


def test_an_ended_shift_is_measured_whole_as_before_round_4(seeded: Session) -> None:
    clock.set_time(NIGHT_END + timedelta(hours=1))
    cancel_roster(seeded, 105)

    result = gap_service.assess_shift(seeded, _night(seeded)).result

    assert result.evaluated_from == NIGHT_START
    assert result.has_gap is True
    assert _slices(seeded) == [(NIGHT_START, NIGHT_END, 4, 1)]


def test_a_cut_source_row_stops_counting_at_its_actual_end(seeded: Session) -> None:
    """Silent-break row (T2, T3): a row cut or cancelled by a move is not on duty after it."""
    cut = NIGHT_START + timedelta(hours=4)
    _row(seeded, 104).actual_end_at = cut
    _row(seeded, 105).status = RosterStatus.CANCELLED
    seeded.flush()

    assert _slices(seeded) == [(NIGHT_START, cut, 4, 1), (cut, NIGHT_END, 3, 2)]
    assert gap_service.assess_shift(seeded, _night(seeded)).result.headcount_gap == 2


def test_a_late_start_counts_only_from_its_actual_start(seeded: Session) -> None:
    start = NIGHT_START + timedelta(hours=2)
    _row(seeded, 105).actual_start_at = start
    seeded.flush()

    assert _slices(seeded) == [(NIGHT_START, start, 4, 1), (start, NIGHT_END, 5, 0)]


def test_record_gap_stores_every_slice_of_all_three_dimensions(seeded: Session) -> None:
    cut = NIGHT_START + timedelta(hours=4)
    # 101 holds ICU in the seed; cutting them also leaves the ICU count short
    _row(seeded, 101).actual_end_at = cut
    case = make_case(seeded)
    record_gap(seeded, case)

    gap = seeded.scalars(select(StaffingGap).where(StaffingGap.case_id == case.id)).one()
    assert gap.evaluated_from == NIGHT_START
    assert gap.headcount_gap == 1
    heads = seeded.execute(
        select(
            StaffingGapInterval.start_at,
            StaffingGapInterval.end_at,
            StaffingGapInterval.current_count,
            StaffingGapInterval.gap_count,
        )
        .where(StaffingGapInterval.gap_id == gap.id)
        .order_by(StaffingGapInterval.start_at)
    ).all()
    assert [tuple(row) for row in heads] == [
        (NIGHT_START, cut, 5, 0),
        (cut, NIGHT_END, 4, 1),
    ]
    roles = seeded.execute(
        select(StaffingGapRoleInterval.role_id, StaffingGapRoleInterval.gap_count)
        .where(StaffingGapRoleInterval.gap_id == gap.id)
        .order_by(StaffingGapRoleInterval.start_at)
    ).all()
    assert [tuple(row) for row in roles] == [(RN, 0), (RN, 1)]
    skills = seeded.execute(
        select(StaffingGapSkillInterval.skill_id, StaffingGapSkillInterval.gap_count)
        .where(StaffingGapSkillInterval.gap_id == gap.id)
        .order_by(StaffingGapSkillInterval.start_at)
    ).all()
    assert [tuple(row) for row in skills] == [(ICU, 0), (ICU, 1)]


def test_case_gap_reads_the_short_slices_back(seeded: Session) -> None:
    cut = NIGHT_START + timedelta(hours=4)
    _row(seeded, 101).actual_end_at = cut
    case = make_case(seeded)
    record_gap(seeded, case)

    intervals = gap_service.get_case_gap(seeded, case.id).intervals

    assert [(i.start_at, i.end_at, i.headcount_gap) for i in intervals] == [
        (NIGHT_START, cut, 0),
        (cut, NIGHT_END, 1),
    ]
    assert [(dict(i.role_gaps), dict(i.skill_gaps)) for i in intervals] == [
        ({}, {}),
        ({RN: 1}, {ICU: 1}),
    ]


def test_a_gap_without_slices_is_short_for_the_whole_shift(seeded: Session) -> None:
    case, _ = short_case(seeded, 105)
    gap = seeded.scalars(select(StaffingGap).where(StaffingGap.case_id == case.id)).one()
    # A gap written before round 4 has no slices and no evaluated_from
    seeded.execute(delete(StaffingGapInterval).where(StaffingGapInterval.gap_id == gap.id))
    seeded.execute(delete(StaffingGapRoleInterval).where(StaffingGapRoleInterval.gap_id == gap.id))
    seeded.execute(
        delete(StaffingGapSkillInterval).where(StaffingGapSkillInterval.gap_id == gap.id)
    )
    gap.evaluated_from = None
    seeded.flush()

    intervals = gap_service.get_case_gap(seeded, case.id).intervals

    assert [(i.start_at, i.end_at, i.headcount_gap, dict(i.role_gaps)) for i in intervals] == [
        (NIGHT_START, NIGHT_END, 1, {RN: 1})
    ]


def test_a_replacement_for_part_of_the_shift_does_not_resolve_the_case(seeded: Session) -> None:
    """Silent-break row (T3): RESOLVED is decided per slice, not from the summary."""
    case, items = short_case(seeded, 105)
    approval(seeded, case, items[201], approved=True)
    row = replacement(seeded, items[201])
    row.actual_end_at = NIGHT_START + timedelta(hours=4)
    seeded.flush()

    facts = case_facts_service.load_case_facts(seeded, case)
    assert facts.gap_closed_by_assigned is False

    row.actual_end_at = None
    seeded.flush()
    assert case_facts_service.load_case_facts(seeded, case).gap_closed_by_assigned is True


def test_a_pending_candidate_covers_only_their_cover_window(seeded: Session) -> None:
    case, items = short_case(seeded, 105)
    item = items[201]
    item.cover_start_at = NIGHT_START + timedelta(hours=4)
    item.cover_end_at = NIGHT_END
    approval(seeded, case, item)
    seeded.flush()

    assert case_facts_service.load_case_facts(seeded, case).gap_closed_with_pending is False

    item.cover_start_at = item.cover_end_at = None
    seeded.flush()
    assert case_facts_service.load_case_facts(seeded, case).gap_closed_with_pending is True


SCENARIOS = (
    "golden_case",
    "candidate_reject",
    "head_nurse_reject",
    "merge_gap",
    "no_feasible_solution",
    "safety_failure",
    "soft_constraint",
    "threshold",
)


def _old_and_new(db: Session, shift: Shift) -> tuple[GapResult, GapResult]:
    requirement = requirement_service.get_current_requirement(db, shift.id)
    old = calculate_gap(
        shift_id=shift.id,
        required_staff=requirement.requirement.required_staff,
        minimum_staff=requirement.requirement.minimum_staff,
        preserve_minimum_staffing=policy_service.get_hard_constraint_policy(
            db
        ).preserve_minimum_staffing,
        required_roles=requirement.required_roles,
        required_skills=requirement.required_skills,
        roster=gap_service.load_roster(db, shift.id),
    )
    return old, gap_service.assess_shift(db, shift).result


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_shifts_without_moves_keep_the_old_gap(seeded: Session, scenario: str) -> None:
    """Silent-break row (T3): the Golden Case and every seed scenario give the same gap.

    Checked on every shift as seeded, and again with each covering person gone.
    """
    if scenario != "golden_case":
        importlib.import_module(f"app.seed.scenarios.{scenario}").seed(seeded)
        seeded.flush()

    checked = 0
    for shift in seeded.scalars(select(Shift).order_by(Shift.id)):
        try:
            requirement_service.get_current_requirement(seeded, shift.id)
        except RequirementNotFoundError:
            continue
        rows = seeded.scalars(
            select(RosterAssignment).where(
                RosterAssignment.shift_id == shift.id,
                RosterAssignment.status.in_(COVERING_ROSTER_STATUSES),
            )
        ).all()
        for gone in (None, *rows):
            if gone is not None:
                previous, gone.status = gone.status, RosterStatus.CANCELLED
                seeded.flush()
            old, new = _old_and_new(seeded, shift)
            assert (new.headcount_gap, dict(new.role_gaps), dict(new.skill_gaps)) == (
                old.headcount_gap,
                dict(old.role_gaps),
                dict(old.skill_gaps),
            )
            assert new.has_gap is old.has_gap
            assert [(i.start_at, i.end_at) for i in new.intervals] == [
                (new.evaluated_from, shift.end_at)
            ]
            checked += 1
            if gone is not None:
                gone.status = previous
                seeded.flush()
    assert checked > 0


def test_case_detail_returns_the_slices_with_names(seeded: Session) -> None:
    cut = NIGHT_START + timedelta(hours=4)
    _row(seeded, 101).actual_end_at = cut
    case = make_case(seeded)
    record_gap(seeded, case)
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        body = TestClient(app).get(f"/cases/{case.id}").json()
    finally:
        app.dependency_overrides.clear()

    gap = body["gap"]
    assert gap["evaluated_from"] == NIGHT_START.isoformat()
    assert gap["headcount_gap"] == 1
    assert gap["intervals"] == [
        {
            "start_at": NIGHT_START.isoformat(),
            "end_at": cut.isoformat(),
            "headcount": {"required_count": 5, "current_count": 5, "gap_count": 0},
            "roles": [
                {"id": RN, "name": "RN", "required_count": 5, "current_count": 5, "gap_count": 0}
            ],
            "skills": [
                {"id": ICU, "name": "ICU", "required_count": 2, "current_count": 2, "gap_count": 0}
            ],
        },
        {
            "start_at": cut.isoformat(),
            "end_at": NIGHT_END.isoformat(),
            "headcount": {"required_count": 5, "current_count": 4, "gap_count": 1},
            "roles": [
                {"id": RN, "name": "RN", "required_count": 5, "current_count": 4, "gap_count": 1}
            ],
            "skills": [
                {"id": ICU, "name": "ICU", "required_count": 2, "current_count": 1, "gap_count": 1}
            ],
        },
    ]
