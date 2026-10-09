"""requirement_service and gap_service on the seeded Golden Case (workflow.md 6.4, seam 10)."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    RosterAssignment,
    Shift,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffingRequirementSkill,
)
from app.domain.enums import RosterStatus
from app.services import gap_service, requirement_service
from app.services.requirement_service import RequirementNotFoundError

RN, ICU = 1, 1
NIGHT_SHIFT, DAY_SHIFT = 1, 2


def _shift(db: Session, shift_id: int) -> Shift:
    shift = db.get(Shift, shift_id)
    assert shift is not None
    return shift


def _cancel(db: Session, staff_id: int, shift_id: int) -> None:
    row = db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == shift_id
        )
    ).one()
    row.status = RosterStatus.CANCELLED


def test_requirement_of_the_night_shift_matches_the_seed(seeded: Session) -> None:
    current = requirement_service.get_current_requirement(seeded, NIGHT_SHIFT)

    assert current.requirement.shift_id == NIGHT_SHIFT
    assert current.required_roles == {RN: 5}
    assert current.required_skills == {ICU: 2}


def test_requirement_without_skills_has_an_empty_skill_map(seeded: Session) -> None:
    current = requirement_service.get_current_requirement(seeded, DAY_SHIFT)

    assert current.required_roles == {RN: 1}
    assert current.required_skills == {}


def test_latest_requirement_is_the_highest_id_even_with_equal_times(seeded: Session) -> None:
    """The demo clock is frozen, so a new version has the same created_at as the old one."""
    old = requirement_service.get_current_requirement(seeded, NIGHT_SHIFT).requirement
    new = StaffingRequirement(shift_id=NIGHT_SHIFT, required_staff=6, minimum_staff=5)
    seeded.add(new)
    seeded.flush()
    seeded.add_all(
        [
            StaffingRequirementRole(staffing_requirement_id=new.id, role_id=RN, required_count=6),
            StaffingRequirementSkill(
                staffing_requirement_id=new.id, skill_id=ICU, required_count=3
            ),
        ]
    )
    seeded.flush()
    assert new.created_at == old.created_at

    current = requirement_service.get_current_requirement(seeded, NIGHT_SHIFT)

    assert current.requirement.id == new.id
    assert current.required_roles == {RN: 6}
    assert current.required_skills == {ICU: 3}


def test_shift_without_a_requirement_raises(seeded: Session) -> None:
    with pytest.raises(RequirementNotFoundError, match="999"):
        requirement_service.get_current_requirement(seeded, 999)


def test_night_shift_has_no_gap_before_anyone_leaves(seeded: Session) -> None:
    assessment = gap_service.assess_shift(seeded, _shift(seeded, NIGHT_SHIFT))

    assert assessment.result.has_gap is False
    assert assessment.result.minimum_required_staff == 5
    assert assessment.patient_count == 10
    assert assessment.patients_per_nurse == 2


def test_night_shift_is_one_nurse_short_after_105_is_cancelled(seeded: Session) -> None:
    _cancel(seeded, 105, NIGHT_SHIFT)  # not flushed: assess_shift must flush first

    assessment = gap_service.assess_shift(seeded, _shift(seeded, NIGHT_SHIFT))

    assert assessment.result.has_gap is True
    assert assessment.result.headcount_gap == 1
    assert assessment.result.role_gaps[RN].gap_count == 1
    assert assessment.result.skill_gaps[ICU].gap_count == 0


def test_losing_an_icu_nurse_is_also_a_skill_gap(seeded: Session) -> None:
    _cancel(seeded, 102, NIGHT_SHIFT)

    assessment = gap_service.assess_shift(seeded, _shift(seeded, NIGHT_SHIFT))

    assert assessment.result.skill_gaps[ICU].gap_count == 1


def test_day_shift_still_has_no_gap_after_203_is_cancelled(seeded: Session) -> None:
    _cancel(seeded, 203, DAY_SHIFT)

    assessment = gap_service.assess_shift(seeded, _shift(seeded, DAY_SHIFT))

    assert assessment.result.has_gap is False


def test_assessment_uses_the_requirement_from_the_shared_loader(seeded: Session) -> None:
    current = requirement_service.get_current_requirement(seeded, NIGHT_SHIFT)

    assessment = gap_service.assess_shift(seeded, _shift(seeded, NIGHT_SHIFT))

    assert assessment.shift_requirement.requirement.id == current.requirement.id


def test_assessment_works_with_production_session_settings(production_seeded: Session) -> None:
    db = production_seeded
    assert db.autoflush is False
    _cancel(db, 105, NIGHT_SHIFT)

    assessment = gap_service.assess_shift(db, _shift(db, NIGHT_SHIFT))

    assert assessment.result.headcount_gap == 1
