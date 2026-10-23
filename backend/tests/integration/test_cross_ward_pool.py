"""The Solver pool across wards (round 4 PR C1, docs/workflow.md section 6.19).

Each test is a row of the silent-failure table of "สถานะของรอบ 4". Wards and staff
get IDs above the highest in use, so a seed that gains rows does not clash.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CandidatePlan,
    RosterAssignment,
    Shift,
    Staff,
    StaffingRequirement,
    StaffSkill,
    Ward,
)
from app.domain.constraints.codes import HardRuleCode
from app.domain.constraints.score_breakdown import score_from_snapshot, weights_from_snapshot
from app.domain.enums import (
    AssignmentType,
    CandidateSource,
    CaseStatus,
    RosterStatus,
    ShiftType,
    StaffStatus,
)
from app.services import optimization_service
from tests.integration.case_rows import RN, leave, make_case, record_gap
from tests.integration.conftest import DEMO_NOW

NIGHT_SHIFT = 1


def _plan(db: Session) -> optimization_service.PlanResult:
    """Plan the night shift after 105 leaves: one RN short."""
    leave(db, 105)
    case = make_case(db, CaseStatus.OPTIMIZING)
    record_gap(db, case)
    return optimization_service.create_plan(db, case)


def _next_id(db: Session, model: Any) -> int:
    return (db.scalar(select(func.max(model.id))) or 0) + 1


def _ward(db: Session, *, active: bool = True, float_pool: bool = False) -> int:
    ward_id = _next_id(db, Ward)
    db.add(
        Ward(
            id=ward_id,
            name=f"Ward {ward_id}",
            is_active=active,
            is_float_pool=float_pool,
            created_at=DEMO_NOW,
            updated_at=DEMO_NOW,
        )
    )
    db.flush()
    return ward_id


def _rn(db: Session, ward_id: int) -> int:
    """An active RN with the ICU and BLS skills, so only the pool rule can leave them out."""
    staff_id = _next_id(db, Staff)
    db.add(
        Staff(
            id=staff_id,
            first_name="Lent",
            last_name="Nurse",
            email=f"{staff_id}@demo.local",
            password_hash="!",
            role_id=RN,
            home_ward_id=ward_id,
            status=StaffStatus.ACTIVE,
            created_at=DEMO_NOW,
            updated_at=DEMO_NOW,
        )
    )
    db.flush()
    db.add_all(StaffSkill(staff_id=staff_id, skill_id=skill_id) for skill_id in (1, 2))
    db.flush()
    return staff_id


def _shift(db: Session, ward_id: int, start_at: datetime, end_at: datetime) -> int:
    shift_id = _next_id(db, Shift)
    db.add(
        Shift(
            id=shift_id,
            ward_id=ward_id,
            patient_count=5,
            start_at=start_at,
            end_at=end_at,
            shift_type=ShiftType.NIGHT,
            is_active=True,
            merge_window_seconds=0,
        )
    )
    db.flush()
    return shift_id


def _duty(
    db: Session,
    staff_id: int,
    shift_id: int,
    *,
    status: RosterStatus = RosterStatus.ASSIGNED,
    actual_end_at: datetime | None = None,
) -> None:
    db.add(
        RosterAssignment(
            staff_id=staff_id,
            shift_id=shift_id,
            status=status,
            assignment_type=AssignmentType.REGULAR,
            actual_end_at=actual_end_at,
        )
    )
    db.flush()


def _night(db: Session) -> Shift:
    shift = db.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    return shift


def _pooled(result: optimization_service.PlanResult) -> set[int]:
    return {item.staff_id for item in result.items} | {row.staff_id for row in result.skipped}


def _entry(plan: CandidatePlan, staff_id: int) -> dict[str, Any]:
    return next(row for row in plan.input_snapshot["candidates"] if row["staff_id"] == staff_id)


def _source_points(plan: CandidatePlan, staff_id: int) -> int:
    weights = weights_from_snapshot(plan.input_snapshot["weights"])
    terms = score_from_snapshot(weights, _entry(plan, staff_id)).terms
    return int(next(t.points for t in terms if t.name == "candidate_source"))


def test_a_free_nurse_of_another_ward_is_a_cross_ward_candidate(seeded: Session) -> None:
    lent = _rn(seeded, _ward(seeded))

    result = _plan(seeded)

    sources = {item.staff_id: item.source for item in result.items}
    assert sources[lent] is CandidateSource.CROSS_WARD
    assert _entry(result.plan, lent)["source"] == "CROSS_WARD"
    assert _source_points(result.plan, lent) == 3000
    assert _source_points(result.plan, 201) == 0
    # Equal metrics otherwise: the in-ward peers rank first
    rank = {item.staff_id: item.rank for item in result.items}
    assert rank[lent] > max(rank[201], rank[202], rank[203])


def test_a_free_nurse_of_the_float_pool_is_a_float_pool_candidate(seeded: Session) -> None:
    lent = _rn(seeded, _ward(seeded, float_pool=True))

    result = _plan(seeded)

    assert {item.staff_id: item.source for item in result.items}[lent] is CandidateSource.FLOAT_POOL
    assert _entry(result.plan, lent)["source"] == "FLOAT_POOL"
    assert _source_points(result.plan, lent) == 1500


def test_someone_on_another_wards_offset_overlapping_shift_is_in_the_pool_with_a_source(
    seeded: Session,
) -> None:
    """A partly overlapping shift is movable (round 4 PR C3, test_transfer_planning.py)."""
    night = _night(seeded)
    busy = _rn(seeded, _ward(seeded))
    shift_id = _shift(
        seeded,
        _ward(seeded),
        night.start_at - timedelta(hours=2),
        night.end_at - timedelta(hours=2),
    )
    seeded.add(StaffingRequirement(shift_id=shift_id, required_staff=0, minimum_staff=0))
    seeded.flush()
    _duty(seeded, busy, shift_id)

    result = _plan(seeded)

    item = next(item for item in result.items if item.staff_id == busy)
    assert item.source_assignment_id is not None
    assert item.cover_start_at is None and item.cover_end_at is None


def test_someone_on_a_pending_approval_overlapping_shift_is_not_in_the_pool(
    seeded: Session,
) -> None:
    night = _night(seeded)
    busy = _rn(seeded, _ward(seeded))
    shift_id = _shift(
        seeded,
        _ward(seeded),
        night.start_at - timedelta(hours=2),
        night.end_at - timedelta(hours=2),
    )
    _duty(seeded, busy, shift_id, status=RosterStatus.PENDING_APPROVAL)

    result = _plan(seeded)

    assert busy not in _pooled(result)
    assert busy not in {row["staff_id"] for row in result.plan.input_snapshot["candidates"]}
    assert all(item.source_assignment_id is None for item in result.items)
    candidates = result.plan.input_snapshot["candidates"]
    assert all(row["source_assignment_id"] is None for row in candidates)


def test_someone_on_another_wards_equal_time_future_shift_is_in_the_pool_with_a_source(
    seeded: Session,
) -> None:
    """A whole-shift transfer (round 4 PR C2, tests/integration/test_transfer_planning.py)."""
    night = _night(seeded)
    ward_id = _ward(seeded)
    busy = _rn(seeded, ward_id)
    shift_id = _shift(seeded, ward_id, night.start_at, night.end_at)
    seeded.add(StaffingRequirement(shift_id=shift_id, required_staff=0, minimum_staff=0))
    seeded.flush()
    _duty(seeded, busy, shift_id)

    result = _plan(seeded)

    item = next(item for item in result.items if item.staff_id == busy)
    source = seeded.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == busy, RosterAssignment.shift_id == shift_id
        )
    ).one()
    assert item.source_assignment_id == source.id
    assert item.source is CandidateSource.CROSS_WARD


def test_a_duty_that_only_touches_the_shift_keeps_the_person_in_the_pool(seeded: Session) -> None:
    night = _night(seeded)
    lent = _rn(seeded, _ward(seeded))
    shift_id = _shift(seeded, _ward(seeded), night.start_at - timedelta(hours=8), night.start_at)
    _duty(seeded, lent, shift_id)

    assert lent in _pooled(_plan(seeded))


def test_a_cancelled_duty_keeps_the_person_in_the_pool(seeded: Session) -> None:
    night = _night(seeded)
    lent = _rn(seeded, _ward(seeded))
    shift_id = _shift(seeded, _ward(seeded), night.start_at, night.end_at)
    _duty(seeded, lent, shift_id, status=RosterStatus.CANCELLED)

    result = _plan(seeded)

    assert lent in {item.staff_id for item in result.items}


def test_actual_times_decide_the_overlap(seeded: Session) -> None:
    """The shift overlaps the night shift, but the person left it before the night shift starts."""
    night = _night(seeded)
    lent = _rn(seeded, _ward(seeded))
    shift_id = _shift(seeded, _ward(seeded), night.start_at - timedelta(hours=4), night.end_at)
    _duty(seeded, lent, shift_id, actual_end_at=night.start_at - timedelta(hours=1))

    assert lent in _pooled(_plan(seeded))


def test_staff_of_an_inactive_ward_are_not_in_the_pool(seeded: Session) -> None:
    closed = _rn(seeded, _ward(seeded, active=False))

    assert closed not in _pooled(_plan(seeded))


def test_a_same_ward_person_on_another_wards_pending_overlapping_shift_is_still_skipped(
    seeded: Session,
) -> None:
    night = _night(seeded)
    shift_id = _shift(seeded, _ward(seeded), night.start_at - timedelta(hours=2), night.end_at)
    _duty(seeded, 201, shift_id, status=RosterStatus.PENDING_APPROVAL)

    result = _plan(seeded)

    reasons = {row.staff_id: row.reason for row in result.skipped}
    assert reasons[201] == HardRuleCode.SHIFT_CONFLICT.value
    assert 201 not in {item.staff_id for item in result.items}
