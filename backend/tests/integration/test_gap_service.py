"""requirement_service and gap_service on the seeded Golden Case (workflow.md 6.4, seam 10)."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    HardConstraintPolicy,
    RosterAssignment,
    Shift,
    StaffingCase,
    StaffingEvent,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffingRequirementSkill,
)
from app.domain.enums import CaseStatus, EventStatus, EventType, RosterStatus
from app.services import gap_service, requirement_service
from app.services.gap_service import GapNotFoundError
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
    assert assessment.result.effective_minimum == 5


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


# --------------------------------------------------------------------------- #
# Headcount target: required_staff, minimum_staff and the policy flag
# (workflow.md section 3.6)
# --------------------------------------------------------------------------- #
def _set_requirement(db: Session, shift_id: int, *, required: int, minimum: int) -> None:
    requirement = requirement_service.get_current_requirement(db, shift_id).requirement
    requirement.required_staff = required
    requirement.minimum_staff = minimum


def _policy(db: Session) -> HardConstraintPolicy:
    policy = db.get(HardConstraintPolicy, 1)
    assert policy is not None
    return policy


def test_headcount_target_is_the_stored_required_staff_not_the_patient_count(
    seeded: Session,
) -> None:
    """The gap reads the requirement. Changing patients alone does not move it."""
    shift = _shift(seeded, NIGHT_SHIFT)
    shift.patient_count = 40  # would need 20 nurses at ratio 2

    assessment = gap_service.assess_shift(seeded, shift)

    assert assessment.result.effective_minimum == 5
    assert assessment.result.headcount_gap == 0


def test_minimum_staff_above_required_staff_is_a_gap_while_the_flag_is_on(
    seeded: Session,
) -> None:
    """Day shift: 2 patients need 1 nurse, 2 are assigned, but the floor is raised to 3."""
    _set_requirement(seeded, DAY_SHIFT, required=1, minimum=3)
    assert _policy(seeded).preserve_minimum_staffing is True

    assessment = gap_service.assess_shift(seeded, _shift(seeded, DAY_SHIFT))

    assert assessment.result.effective_minimum == 3
    assert assessment.result.headcount_gap == 1
    assert assessment.result.has_gap is True


def test_minimum_staff_is_ignored_while_the_flag_is_off(seeded: Session) -> None:
    _set_requirement(seeded, DAY_SHIFT, required=1, minimum=3)
    _policy(seeded).preserve_minimum_staffing = False

    assessment = gap_service.assess_shift(seeded, _shift(seeded, DAY_SHIFT))

    assert assessment.result.effective_minimum == 1
    assert assessment.result.has_gap is False


def test_assessment_reads_the_flag_with_production_session_settings(
    production_seeded: Session,
) -> None:
    """Autoflush is off: the unflushed requirement and policy edits must still be seen."""
    db = production_seeded
    _set_requirement(db, DAY_SHIFT, required=1, minimum=3)
    _policy(db).preserve_minimum_staffing = False

    assessment = gap_service.assess_shift(db, _shift(db, DAY_SHIFT))

    assert assessment.result.effective_minimum == 1


# --------------------------------------------------------------------------- #
# get_case_gap: the one loader for the Solver and Safety (workflow.md 6.4, seam 11)
# --------------------------------------------------------------------------- #
def _case_with_gap(db: Session, *cancelled_staff: int) -> StaffingCase:
    """A case on the night shift whose gap was recorded after the given staff left."""
    for staff_id in cancelled_staff:
        _cancel(db, staff_id, NIGHT_SHIFT)
    shift = _shift(db, NIGHT_SHIFT)
    event = StaffingEvent(
        event_type=EventType.STAFF_UNAVAILABLE,
        shift_id=NIGHT_SHIFT,
        occurred_at=shift.start_at,
        staff_id=cancelled_staff[0],
        status=EventStatus.PROCESSED,
    )
    db.add(event)
    db.flush()
    case = StaffingCase(
        event_id=event.id,
        shift_id=NIGHT_SHIFT,
        status=CaseStatus.ASSESSING,
        required_replacement_time=shift.start_at,
    )
    db.add(case)
    db.flush()
    gap_service.record_gap(db, case, gap_service.assess_shift(db, shift))
    return case


def test_case_gap_returns_only_the_roles_and_skills_that_are_short(seeded: Session) -> None:
    """105 has no ICU skill: the case is short one RN, and ICU is still covered."""
    case = _case_with_gap(seeded, 105)

    case_gap = gap_service.get_case_gap(seeded, case.id)

    assert case_gap.headcount_gap == 1
    assert case_gap.gap.effective_minimum == 5
    assert case_gap.role_gaps == {RN: 1}
    assert case_gap.skill_gaps == {}


def test_case_gap_includes_a_skill_shortage(seeded: Session) -> None:
    """101 holds ICU: losing 101 leaves one RN and one ICU nurse missing."""
    case = _case_with_gap(seeded, 101)

    case_gap = gap_service.get_case_gap(seeded, case.id)

    assert case_gap.headcount_gap == 1
    assert case_gap.role_gaps == {RN: 1}
    assert case_gap.skill_gaps == {ICU: 1}


def test_case_gap_is_the_highest_id_and_keeps_its_own_counts(seeded: Session) -> None:
    case = _case_with_gap(seeded, 105)
    _cancel(seeded, 101, NIGHT_SHIFT)
    newer = gap_service.record_gap(
        seeded, case, gap_service.assess_shift(seeded, _shift(seeded, NIGHT_SHIFT))
    )

    case_gap = gap_service.get_case_gap(seeded, case.id)

    assert case_gap.gap.id == newer.id
    assert case_gap.headcount_gap == 2
    assert case_gap.role_gaps == {RN: 2}
    assert case_gap.skill_gaps == {ICU: 1}


def test_case_gap_does_not_read_another_case(seeded: Session) -> None:
    first = _case_with_gap(seeded, 105)
    second = _case_with_gap(seeded, 101)

    assert gap_service.get_case_gap(seeded, first.id).skill_gaps == {}
    assert gap_service.get_case_gap(seeded, second.id).skill_gaps == {ICU: 1}


def test_case_without_a_gap_raises(seeded: Session) -> None:
    with pytest.raises(GapNotFoundError, match="999"):
        gap_service.get_case_gap(seeded, 999)


def test_case_gap_works_with_production_session_settings(production_seeded: Session) -> None:
    db = production_seeded
    case = _case_with_gap(db, 101)

    case_gap = gap_service.get_case_gap(db, case.id)

    assert (case_gap.headcount_gap, case_gap.role_gaps, case_gap.skill_gaps) == (
        1,
        {RN: 1},
        {ICU: 1},
    )
