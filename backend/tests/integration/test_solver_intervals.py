"""Planning and wave selection per time slice (round 4 PR T4).

The seeded night shift runs 23:00 to 07:00 with RNs 101 to 105 and needs 5 RNs and
2 ICU nurses. 201, 202 and 203 are the free RNs of the Golden Case. _covers is
empty in T4 (C2/C3 fill it), so the tests that need a partial or transfer cover
replace it.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CandidateItem,
    CandidateItemTarget,
    CandidatePlan,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
    StaffingRequirement,
    StaffingRequirementSkill,
)
from app.domain.constraints.codes import GAP_TIME_MISMATCH, HardRuleCode
from app.domain.enums import (
    AssignmentType,
    CaseStatus,
    RosterStatus,
    SelectionType,
    ShiftType,
    SolverStatus,
    StaffStatus,
    TargetType,
)
from app.services import optimization_service, wave_service
from app.services.hard_rule_service import Cover
from app.workflow import orchestrator
from app.workflow.handlers import optimize
from tests.integration.case_rows import (
    NIGHT_SHIFT,
    assign,
    cancel_roster,
    make_case,
    make_plan,
    record_gap,
    short_case,
)
from tests.integration.conftest import DEMO_NOW
from tests.integration.test_optimize import _fake_solver

NIGHT_START = DEMO_NOW + timedelta(hours=2)
NIGHT_END = DEMO_NOW + timedelta(hours=10)
CUT = NIGHT_START + timedelta(hours=4)


def _utc(value: datetime) -> str:
    """The gap slices come back from the database in UTC; the snapshot keeps that text."""
    return value.astimezone(UTC).isoformat()


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


def _plan(db: Session, case: StaffingCase) -> CandidatePlan:
    return db.scalars(select(CandidatePlan).where(CandidatePlan.case_id == case.id)).one()


def _items(db: Session, plan: CandidatePlan) -> dict[int, CandidateItem]:
    return {
        item.staff_id: item
        for item in db.scalars(select(CandidateItem).where(CandidateItem.plan_id == plan.id))
    }


def _optimizing_case(db: Session) -> StaffingCase:
    case = make_case(db, CaseStatus.OPTIMIZING)
    record_gap(db, case)
    return case


def _two_slice_case(db: Session) -> StaffingCase:
    """105 is gone and 104 leaves at CUT: one RN short before it, two after."""
    cancel_roster(db, 105)
    _row(db, 104).actual_end_at = CUT
    db.flush()
    return _optimizing_case(db)


def _late_start_case(db: Session) -> StaffingCase:
    """105 starts at CUT: the only short slice is the one before it."""
    _row(db, 105).actual_start_at = CUT
    db.flush()
    return _optimizing_case(db)


def _use_covers(monkeypatch: pytest.MonkeyPatch, covers: dict[int, Cover]) -> None:
    monkeypatch.setattr(optimization_service, "_covers", lambda db, shift, pool: covers)


def _source_shift(db: Session) -> Shift:
    night = _night(db)
    source = Shift(
        ward_id=1,
        patient_count=2,
        start_at=night.start_at,
        end_at=night.end_at,
        shift_type=ShiftType.NIGHT,
        is_active=True,
    )
    db.add(source)
    db.flush()
    # The source shift is judged like a case (round 4 PR C2): it needs a requirement
    db.add(StaffingRequirement(shift_id=source.id, required_staff=0, minimum_staff=0))
    db.flush()
    return source


def _source_row(db: Session, source: Shift, staff_id: int) -> RosterAssignment:
    row = RosterAssignment(
        staff_id=staff_id,
        shift_id=source.id,
        status=RosterStatus.ASSIGNED,
        assignment_type=AssignmentType.REGULAR,
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------- #
# create_plan on a multi-slice gap
# --------------------------------------------------------------------------- #
def test_the_solver_gets_the_short_slices_and_the_snapshot_keeps_them(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _two_slice_case(seeded)
    calls = _fake_solver(monkeypatch, SolverStatus.OPTIMAL)

    optimize.handle(seeded, case)

    [call] = calls
    assert [(i.start_at, i.end_at, i.headcount_gap) for i in call["intervals"]] == [
        (NIGHT_START, CUT, 1),
        (CUT, NIGHT_END, 2),
    ]
    plan = _plan(seeded, case)
    snapshot = plan.input_snapshot
    assert snapshot["partial_plan"] is False
    assert snapshot["intervals"] == [
        {
            "start_at": _utc(NIGHT_START),
            "end_at": _utc(CUT),
            "headcount": {"gap": 1, "target": 2},
            "roles": [{"role_id": 1, "gap": 1, "target": 2}],
            "skills": [],
        },
        {
            "start_at": _utc(CUT),
            "end_at": _utc(NIGHT_END),
            "headcount": {"gap": 2, "target": 3},
            "roles": [{"role_id": 1, "gap": 2, "target": 3}],
            "skills": [],
        },
    ]
    # The summary targets are unchanged: the largest gap of any slice
    assert snapshot["targets"]["headcount"] == {"gap": 2, "target": 3}
    entries = {row["staff_id"]: row for row in snapshot["candidates"]}
    assert all(("credits" in row) is row["first_wave"] for row in entries.values())
    assert any(row["first_wave"] for row in entries.values())


def test_the_golden_case_plan_is_unchanged_and_credits_cover_the_shift(seeded: Session) -> None:
    cancel_roster(seeded, 105)
    case = _optimizing_case(seeded)

    optimize.handle(seeded, case)

    plan = _plan(seeded, case)
    assert plan.solver_status is SolverStatus.OPTIMAL
    assert plan.objective_score == 20220
    snapshot = plan.input_snapshot
    assert snapshot["partial_plan"] is False
    assert len(snapshot["intervals"]) == 1
    assert snapshot["intervals"][0]["start_at"] == _utc(NIGHT_START)
    assert snapshot["intervals"][0]["end_at"] == _utc(NIGHT_END)
    assert [row["staff_id"] for row in snapshot["candidates"]] == [201, 202, 203]
    assert [row["first_wave"] for row in snapshot["candidates"]] == [True, True, False]
    first = snapshot["candidates"][0]
    assert first["credits"] == [
        {
            "target_type": "ROLE",
            "selection_type": "PRIMARY",
            "role_id": 1,
            "skill_id": None,
            "start_at": _utc(NIGHT_START),
            "end_at": _utc(NIGHT_END),
        },
        {
            "target_type": "HEADCOUNT",
            "selection_type": "PRIMARY",
            "role_id": None,
            "skill_id": None,
            "start_at": _utc(NIGHT_START),
            "end_at": _utc(NIGHT_END),
        },
    ]
    assert "credits" not in snapshot["candidates"][2]


# --------------------------------------------------------------------------- #
# _covers: a partial cover
# --------------------------------------------------------------------------- #
def test_a_cover_outside_every_short_slice_is_skipped_as_gap_time_mismatch(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _late_start_case(seeded)
    # 201 can only come once the shift is already full again
    _use_covers(monkeypatch, {201: Cover(CUT, NIGHT_END, None)})

    optimize.handle(seeded, case)

    plan = _plan(seeded, case)
    assert {"staff_id": 201, "reason": GAP_TIME_MISMATCH} in plan.input_snapshot["skipped"]
    assert 201 not in _items(seeded, plan)
    assert GAP_TIME_MISMATCH not in {rule.value for rule in HardRuleCode}


def test_a_cover_inside_a_short_slice_is_planned_and_written(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _late_start_case(seeded)
    _use_covers(monkeypatch, {202: Cover(NIGHT_START, CUT, None)})

    optimize.handle(seeded, case)

    plan = _plan(seeded, case)
    items = _items(seeded, plan)
    assert items[202].cover_start_at == NIGHT_START
    assert items[202].cover_end_at == CUT
    assert items[202].source_assignment_id is None
    assert items[201].cover_start_at is None
    entries = {row["staff_id"]: row for row in plan.input_snapshot["candidates"]}
    assert entries[202]["cover_start_at"] == NIGHT_START.isoformat()
    assert entries[202]["cover_end_at"] == CUT.isoformat()
    assert entries[201]["cover_start_at"] is None
    assert {"staff_id": 202, "reason": GAP_TIME_MISMATCH} not in plan.input_snapshot["skipped"]


def test_the_cover_is_a_window_for_the_nothing_to_fill_check(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A skill short in one slice only: 202 has no ICU, so a cover of that slice skips them."""
    requirement = seeded.get(StaffingRequirementSkill, (1, 1))
    assert requirement is not None
    requirement.required_count = 3
    seeded.flush()
    case = _optimizing_case(seeded)
    _use_covers(monkeypatch, {202: Cover(NIGHT_START, CUT, None)})

    optimize.handle(seeded, case)

    plan = _plan(seeded, case)
    assert {"staff_id": 202, "reason": HardRuleCode.SKILL_MISMATCH.value} in plan.input_snapshot[
        "skipped"
    ]


# --------------------------------------------------------------------------- #
# Two transfer covers from the same source shift: a partial plan
# --------------------------------------------------------------------------- #
def _transfer_case(db: Session, monkeypatch: pytest.MonkeyPatch) -> StaffingCase:
    """201 and 202 both come off one other shift; 203 is out, so one RN is all we can get."""
    staff = db.get(Staff, 203)
    assert staff is not None
    staff.status = StaffStatus.INACTIVE
    cancel_roster(db, 105)
    cancel_roster(db, 104)
    source = _source_shift(db)
    start = NIGHT_START + timedelta(hours=2)
    _use_covers(
        monkeypatch,
        {
            staff_id: Cover(start, NIGHT_END, _source_row(db, source, staff_id).id)
            for staff_id in (201, 202)
        },
    )
    return _optimizing_case(db)


def test_candidates_of_one_source_shift_give_a_partial_plan(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _transfer_case(seeded, monkeypatch)

    result = optimize.handle(seeded, case)

    assert result.next_status is CaseStatus.OUTREACH
    plan = _plan(seeded, case)
    assert plan.solver_status is SolverStatus.OPTIMAL
    assert plan.input_snapshot["partial_plan"] is True
    entries = plan.input_snapshot["candidates"]
    assert len(entries) == 2
    assert [row["first_wave"] for row in entries] == [True, False]
    assert all(row["source_assignment_id"] is not None for row in entries)
    items = _items(seeded, plan)
    assert all(item.source_assignment_id is not None for item in items.values())
    assert all(item.cover_end_at == NIGHT_END for item in items.values())


def test_the_orchestrator_goes_on_with_a_partial_plan(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _transfer_case(seeded, monkeypatch)

    orchestrator.advance(seeded, case.id)

    seeded.expire_all()
    assert case.status is not CaseStatus.FAILED
    assert case.status is CaseStatus.WAITING_RESPONSE
    plan = _plan(seeded, case)
    assert plan.solver_status is not SolverStatus.MODEL_INVALID
    assert plan.input_snapshot["partial_plan"] is True


# --------------------------------------------------------------------------- #
# select_wave per slice
# --------------------------------------------------------------------------- #
def test_the_next_wave_fills_the_slice_nobody_covers_yet(seeded: Session) -> None:
    """Slice 1 is closed by 201's partial row; only 202 covers slice 2, so 203 is not needed."""
    cancel_roster(seeded, 105)
    _row(seeded, 104).actual_end_at = CUT
    seeded.flush()
    case = make_case(seeded)
    record_gap(seeded, case)
    items = make_plan(seeded, case)
    assign(seeded, case, items[201])
    # assign() wrote the roster row after approving; cut it at CUT
    rows = seeded.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == 201,
            RosterAssignment.shift_id == NIGHT_SHIFT,
            RosterAssignment.assignment_type == AssignmentType.REPLACEMENT,
        )
    ).all()
    assert len(rows) == 1
    rows[0].actual_end_at = CUT
    items[202].cover_start_at, items[202].cover_end_at = CUT, NIGHT_END
    items[203].cover_start_at, items[203].cover_end_at = NIGHT_START, CUT
    seeded.flush()

    selection = wave_service.select_wave(seeded, case_id=case.id, shift=_night(seeded))

    assert [item.staff_id for item in selection.items] == [202]
    assert _targets_of(seeded, items[202]) != []
    assert _targets_of(seeded, items[203]) == []


def test_a_candidate_with_a_whole_shift_cover_is_still_chosen_per_slice(seeded: Session) -> None:
    """Legacy: no covers, one slice. The wave is the one the summary counts gave."""
    case, items = short_case(seeded, 105)

    selection = wave_service.select_wave(seeded, case_id=case.id, shift=_night(seeded))

    assert [item.staff_id for item in selection.items] == [201, 202]


def _targets_of(db: Session, item: CandidateItem) -> list[tuple[Any, Any]]:
    return [
        (row.target_type, row.selection_type)
        for row in db.scalars(
            select(CandidateItemTarget)
            .where(CandidateItemTarget.candidate_item_id == item.id)
            .order_by(CandidateItemTarget.id)
        )
    ]


def test_the_wave_writes_target_rows_for_the_chosen_only(seeded: Session) -> None:
    case, items = short_case(seeded, 105)

    wave_service.select_wave(seeded, case_id=case.id, shift=_night(seeded))

    assert _targets_of(seeded, items[201]) == [
        (TargetType.ROLE, SelectionType.PRIMARY),
        (TargetType.HEADCOUNT, SelectionType.PRIMARY),
    ]
    assert _targets_of(seeded, items[203]) == []
