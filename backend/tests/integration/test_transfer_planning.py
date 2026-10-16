"""Planning and wave selection of a transfer (round 4 PR C2 and C3, workflow.md 6.19).

A nurse whose only duty overlapping the short shift is an ASSIGNED row on another
ward's shift is movable while a move is still possible (C3; C2 allowed only an equal,
not started shift): she enters the Pool with her roster row as the source assignment
and a cover from the move time to the end of the short shift. Each test is a row of
the silent-failure table of "สถานะของรอบ 4".
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    CandidateItem,
    CandidateOutreach,
    RosterAssignment,
    Staff,
    StaffingCase,
    StaffingRequirement,
    StaffingRequirementRole,
    StaffingRequirementSkill,
    StaffSkill,
)
from app.domain.constraints.codes import GAP_TIME_MISMATCH, SOURCE_SHIFT_TAKEN, HardRuleCode
from app.domain.enums import (
    AssignmentType,
    CandidateSource,
    CaseStatus,
    OutreachStatus,
    RosterStatus,
    SolverStatus,
    StaffStatus,
)
from app.services import hard_rule_service, optimization_service, wave_service
from app.services.hard_rule_service import Cover
from tests.integration.case_rows import RN, approval, leave, make_case, offer, record_gap
from tests.integration.test_cross_ward_pool import _duty, _night, _plan, _rn, _shift, _ward

pytestmark = pytest.mark.usefixtures("frozen_clock")

ICU, BLS = 1, 2
VIOLATION = HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION.value


class Scene:
    """A source shift of another ward, by default with the same hours as the night shift.

    `starts` and `ends` move its start and end away from the night shift's.
    """

    def __init__(
        self,
        db: Session,
        *,
        required: int,
        holders: int,
        skill: int | None = None,
        home_ward_id: int | None = None,
        starts: timedelta = timedelta(0),
        ends: timedelta = timedelta(0),
    ) -> None:
        night = _night(db)
        self.db = db
        self.ward_id = _ward(db)
        self.shift_id = _shift(db, self.ward_id, night.start_at + starts, night.end_at + ends)
        requirement = StaffingRequirement(
            shift_id=self.shift_id,
            required_staff=required,
            minimum_staff=required,
            created_at=night.start_at,
        )
        db.add(requirement)
        db.flush()
        db.add(
            StaffingRequirementRole(
                staffing_requirement_id=requirement.id, role_id=RN, required_count=required
            )
        )
        if skill is not None:
            db.add(
                StaffingRequirementSkill(
                    staffing_requirement_id=requirement.id, skill_id=skill, required_count=1
                )
            )
        db.flush()
        self.staff = [_rn(db, home_ward_id or self.ward_id) for _ in range(holders)]
        for staff_id in self.staff:
            _duty(db, staff_id, self.shift_id)

    def row(self, staff_id: int) -> RosterAssignment:
        return self.db.scalars(
            select(RosterAssignment).where(
                RosterAssignment.staff_id == staff_id, RosterAssignment.shift_id == self.shift_id
            )
        ).one()


def _items(result: optimization_service.PlanResult) -> dict[int, CandidateItem]:
    return {item.staff_id: item for item in result.items}


def _skipped(result: optimization_service.PlanResult) -> dict[int, str]:
    return {row.staff_id: row.reason for row in result.skipped}


def _pooled(result: optimization_service.PlanResult) -> set[int]:
    return {*_items(result)} | {*_skipped(result)}


def _drop_skills(db: Session, staff_id: int) -> None:
    for row in db.scalars(select(StaffSkill).where(StaffSkill.staff_id == staff_id)):
        db.delete(row)
    db.flush()


def _case(db: Session, result: optimization_service.PlanResult) -> StaffingCase:
    case = db.get(StaffingCase, result.plan.case_id)
    assert case is not None
    return case


def test_an_equal_time_nurse_on_another_ward_enters_the_pool_with_a_cover_and_source(
    seeded: Session,
) -> None:
    scene = Scene(seeded, required=2, holders=3)

    result = _plan(seeded)

    items = _items(result)
    mover = scene.staff[0]
    assert items[mover].source is CandidateSource.CROSS_WARD
    assert items[mover].source_assignment_id == scene.row(mover).id
    assert items[mover].cover_start_at is None and items[mover].cover_end_at is None
    entry = next(r for r in result.plan.input_snapshot["candidates"] if r["staff_id"] == mover)
    assert entry["source_assignment_id"] == scene.row(mover).id
    # The ward's own peers are not moved
    assert items[201].source_assignment_id is None


def test_a_float_pool_nurse_on_an_equal_time_shift_keeps_her_float_pool_source(
    seeded: Session,
) -> None:
    scene = Scene(seeded, required=1, holders=2, home_ward_id=_ward(seeded, float_pool=True))

    items = _items(_plan(seeded))

    assert items[scene.staff[0]].source is CandidateSource.FLOAT_POOL
    assert items[scene.staff[0]].source_assignment_id == scene.row(scene.staff[0]).id


def test_a_same_ward_nurse_on_another_wards_equal_time_shift_is_moved(seeded: Session) -> None:
    scene = Scene(seeded, required=1, holders=2, home_ward_id=_night(seeded).ward_id)

    item = _items(_plan(seeded))[scene.staff[0]]

    assert item.source is CandidateSource.SAME_WARD
    assert item.source_assignment_id == scene.row(scene.staff[0]).id


def test_a_person_whose_source_shift_has_started_enters_the_pool(seeded: Session) -> None:
    """R4-Q43: a started source shift is a mid-shift move, not a reason to leave the person out."""
    scene = Scene(seeded, required=1, holders=2)
    clock.set_time(_night(seeded).start_at + timedelta(minutes=30))

    item = _items(_plan(seeded))[scene.staff[0]]

    assert item.source_assignment_id == scene.row(scene.staff[0]).id
    # m = the start of the night shift: the cover is the whole shift
    assert item.cover_start_at is None and item.cover_end_at is None


def test_a_source_shift_that_starts_earlier_keeps_its_first_part_as_a_linked_duty(
    seeded: Session,
) -> None:
    scene = Scene(seeded, required=1, holders=2, starts=timedelta(hours=-1))
    night = _night(seeded)

    item = _items(_plan(seeded))[scene.staff[0]]

    assert item.source_assignment_id == scene.row(scene.staff[0]).id
    assert item.cover_start_at is None and item.cover_end_at is None
    context = hard_rule_service.check_items(seeded, shift=night, items=[item])[item.id].context
    assert context.linked_duty is not None
    assert context.linked_duty.shift_id == scene.shift_id
    assert context.linked_duty.start_at == night.start_at - timedelta(hours=1)
    assert context.linked_duty.end_at == night.start_at


def test_a_source_shift_that_starts_later_gives_a_cover_from_its_start(seeded: Session) -> None:
    scene = Scene(seeded, required=1, holders=2, starts=timedelta(hours=1))
    night = _night(seeded)

    result = _plan(seeded)

    item = _items(result)[scene.staff[0]]
    assert item.source_assignment_id == scene.row(scene.staff[0]).id
    assert item.cover_start_at == night.start_at + timedelta(hours=1)
    assert item.cover_end_at == night.end_at
    entry = next(
        r for r in result.plan.input_snapshot["candidates"] if r["staff_id"] == item.staff_id
    )
    assert entry["cover_start_at"] is not None and entry["cover_end_at"] is not None


def test_a_source_row_with_actual_times_is_covered_from_its_effective_times(
    seeded: Session,
) -> None:
    scene = Scene(seeded, required=1, holders=2)
    night = _night(seeded)
    row = scene.row(scene.staff[0])
    row.actual_start_at = night.start_at + timedelta(hours=2)
    row.actual_end_at = night.end_at - timedelta(hours=1)
    seeded.flush()

    item = _items(_plan(seeded))[scene.staff[0]]

    assert item.source_assignment_id == row.id
    assert item.cover_start_at == night.start_at + timedelta(hours=2)
    # The move is permanent: the cover runs to the end of the short shift
    assert item.cover_end_at == night.end_at


def test_a_source_row_that_is_over_by_now_keeps_the_person_out(seeded: Session) -> None:
    scene = Scene(seeded, required=1, holders=2)
    night = _night(seeded)
    scene.row(scene.staff[0]).actual_end_at = night.start_at + timedelta(hours=2)
    seeded.flush()
    clock.set_time(night.start_at + timedelta(hours=3))

    result = _plan(seeded)

    assert scene.staff[0] not in _pooled(result)
    assert scene.staff[1] in _pooled(result)


def test_the_linked_source_part_lets_a_mover_pass_the_rest_rule(seeded: Session) -> None:
    """Silent-failure table, T1 and C3: the cut-off source and the new shift are one duty."""
    night = _night(seeded)
    # 20:00 to 04:00 against the 23:00 to 07:00 night shift: 11 h as one duty
    scene = Scene(
        seeded, required=1, holders=2, starts=timedelta(hours=-3), ends=timedelta(hours=-3)
    )
    mover = scene.staff[0]
    # A shift that ends exactly when the night shift starts, with no transfer link: 0 h of rest
    control = _rn(seeded, _ward(seeded))
    adjacent = _shift(seeded, _ward(seeded), night.start_at - timedelta(hours=8), night.start_at)
    seeded.add(StaffingRequirement(shift_id=adjacent, required_staff=0, minimum_staff=0))
    seeded.flush()
    _duty(seeded, control, adjacent)

    result = _plan(seeded)

    assert mover in _items(result)
    assert _skipped(result)[control] == HardRuleCode.INSUFFICIENT_REST.value


def test_a_mover_whose_cover_misses_every_short_slice_is_skipped(seeded: Session) -> None:
    """GAP_TIME_MISMATCH is reachable since C3: the gap is short only in the first 4 hours."""
    night = _night(seeded)
    scene = Scene(seeded, required=1, holders=2, starts=timedelta(hours=5))
    row_105 = seeded.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id == 105, RosterAssignment.shift_id == night.id
        )
    ).one()
    row_105.actual_start_at = night.start_at + timedelta(hours=4)
    seeded.flush()
    case = make_case(seeded, CaseStatus.OPTIMIZING)
    record_gap(seeded, case)

    result = optimization_service.create_plan(seeded, case)

    assert _skipped(result)[scene.staff[0]] == GAP_TIME_MISMATCH
    assert scene.staff[0] not in _items(result)


def test_a_pending_approval_source_row_keeps_the_person_out(seeded: Session) -> None:
    scene = Scene(seeded, required=1, holders=2)
    scene.row(scene.staff[0]).status = RosterStatus.PENDING_APPROVAL
    seeded.flush()

    result = _plan(seeded)

    assert scene.staff[0] not in _pooled(result)
    assert scene.staff[1] in _pooled(result)


def test_a_person_with_two_overlapping_duties_is_not_movable(seeded: Session) -> None:
    scene = Scene(seeded, required=1, holders=2)
    night = _night(seeded)
    _duty(seeded, scene.staff[0], _shift(seeded, _ward(seeded), night.start_at, night.end_at))

    assert scene.staff[0] not in _pooled(_plan(seeded))


def test_a_source_shift_with_no_surplus_skips_the_candidate(seeded: Session) -> None:
    scene = Scene(seeded, required=2, holders=2)

    result = _plan(seeded)

    skipped = _skipped(result)
    assert skipped[scene.staff[0]] == VIOLATION
    assert skipped[scene.staff[1]] == VIOLATION
    assert not set(scene.staff) & {*_items(result)}


def test_losing_the_only_holder_of_a_skill_fails_the_rule_with_headcount_fine(
    seeded: Session,
) -> None:
    scene = Scene(seeded, required=1, holders=3, skill=ICU)
    holder, others = scene.staff[0], scene.staff[1:]
    for staff_id in others:
        _drop_skills(seeded, staff_id)

    result = _plan(seeded)

    assert _skipped(result)[holder] == VIOLATION
    # Someone without the skill can leave: headcount 3 > 1 and the skill stays held
    assert all(staff_id in _items(result) for staff_id in others)


def test_another_holder_of_the_skill_lets_the_first_leave(seeded: Session) -> None:
    scene = Scene(seeded, required=1, holders=2, skill=ICU)

    result = _plan(seeded)

    assert all(staff_id in _items(result) for staff_id in scene.staff)


def test_planning_and_safety_give_the_same_answer(seeded: Session) -> None:
    scene = Scene(seeded, required=2, holders=3)
    mover = scene.staff[0]
    item = _items(_plan(seeded))[mover]
    night = _night(seeded)
    cover = Cover(None, None, scene.row(mover).id)

    def both() -> tuple[hard_rule_service.CandidateCheck, hard_rule_service.CandidateCheck]:
        planned = hard_rule_service.check_staff(
            seeded, shift=night, staff_ids=[mover], covers={mover: cover}
        )[mover]
        return planned, hard_rule_service.check_items(seeded, shift=night, items=[item])[item.id]

    planned, safety = both()
    assert planned.result.failed_rules == safety.result.failed_rules == ()
    assert safety.context.source_shift is not None
    assert safety.context.source_shift.shift_id == scene.shift_id
    assert not safety.context.source_shift.leaves_gap

    scene.row(scene.staff[1]).status = RosterStatus.CANCELLED
    seeded.flush()
    planned, safety = both()
    assert HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION in planned.result.failed_rules
    assert HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION in safety.result.failed_rules
    assert safety.context.source_shift is not None and safety.context.source_shift.leaves_gap


def test_planning_and_safety_give_the_same_answer_for_a_partial_cover(seeded: Session) -> None:
    scene = Scene(seeded, required=2, holders=3, starts=timedelta(hours=1))
    mover = scene.staff[0]
    item = _items(_plan(seeded))[mover]
    night = _night(seeded)
    cover = Cover(night.start_at + timedelta(hours=1), night.end_at, scene.row(mover).id)
    assert Cover.of(item) == cover

    def both() -> tuple[hard_rule_service.CandidateCheck, hard_rule_service.CandidateCheck]:
        planned = hard_rule_service.check_staff(
            seeded, shift=night, staff_ids=[mover], covers={mover: cover}
        )[mover]
        return planned, hard_rule_service.check_items(seeded, shift=night, items=[item])[item.id]

    planned, safety = both()
    assert planned.result.failed_rules == safety.result.failed_rules == ()
    assert planned.context.proposed_shift == safety.context.proposed_shift
    assert safety.context.source_shift is not None and not safety.context.source_shift.leaves_gap

    scene.row(scene.staff[1]).status = RosterStatus.CANCELLED
    seeded.flush()
    planned, safety = both()
    assert HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION in planned.result.failed_rules
    assert HardRuleCode.SOURCE_WARD_MINIMUM_VIOLATION in safety.result.failed_rules
    assert safety.context.source_shift is not None and safety.context.source_shift.leaves_gap


def test_check_items_with_a_move_time_cuts_the_source_at_that_time(seeded: Session) -> None:
    scene = Scene(seeded, required=1, holders=2)
    item = _items(_plan(seeded))[scene.staff[0]]
    night = _night(seeded)
    moved_at = night.start_at + timedelta(hours=3)

    checked = hard_rule_service.check_items(
        seeded, shift=night, items=[item], move_at={item.id: moved_at}
    )[item.id]

    assert checked.context.proposed_shift.start_at == moved_at
    assert checked.context.proposed_shift.end_at == night.end_at
    assert checked.context.linked_duty is not None
    assert checked.context.linked_duty.end_at == moved_at


# --------------------------------------------------------------------------- #
# R4-Q37: candidates of one source shift exclude each other
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("second_skills", [(ICU, BLS), (BLS,)])
def test_two_candidates_of_one_source_shift_give_a_partial_plan(
    seeded: Session, second_skills: tuple[int, ...]
) -> None:
    scene = Scene(seeded, required=2, holders=4)
    first, second = scene.staff[:2]
    _drop_skills(seeded, second)
    seeded.add_all(StaffSkill(staff_id=second, skill_id=skill) for skill in second_skills)
    # Nobody else can fill the two seats
    for staff_id in (201, 202, 203):
        staff = seeded.get(Staff, staff_id)
        assert staff is not None
        staff.status = StaffStatus.INACTIVE
    leave(seeded, 104)
    leave(seeded, 105)
    case = make_case(seeded, CaseStatus.OPTIMIZING)
    record_gap(seeded, case)

    result = optimization_service.create_plan(seeded, case)

    assert result.plan.solver_status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    assert result.plan.input_snapshot["partial_plan"] is True
    items = _items(result)
    assert items[first].source_assignment_id is not None
    assert items[second].source_assignment_id is not None
    first_wave = {
        row["staff_id"] for row in result.plan.input_snapshot["candidates"] if row["first_wave"]
    }
    assert len(first_wave & set(scene.staff)) == 1


# --------------------------------------------------------------------------- #
# SOURCE_SHIFT_TAKEN in wave selection
# --------------------------------------------------------------------------- #
def _movers(db: Session) -> tuple[Scene, optimization_service.PlanResult, StaffingCase]:
    """A source shift with 4 holders and a target of 2; the destination is short by one."""
    scene = Scene(db, required=2, holders=4)
    result = _plan(db)
    return scene, result, _case(db, result)


def test_one_wave_never_picks_two_people_of_one_source_shift(seeded: Session) -> None:
    scene, result, case = _movers(seeded)

    selection = wave_service.select_wave(seeded, case_id=case.id, shift=_night(seeded))

    chosen = [item.staff_id for item in selection.items if item.staff_id in scene.staff]
    assert len(chosen) <= 1


@pytest.mark.parametrize("status", [OutreachStatus.SENT, OutreachStatus.ACCEPTED])
def test_a_live_offer_or_pending_request_takes_the_source_shift(
    seeded: Session, status: OutreachStatus
) -> None:
    scene, result, case = _movers(seeded)
    first, second = scene.staff[:2]
    offer(seeded, case, _items(result)[first], status)

    selection = wave_service.select_wave(seeded, case_id=case.id, shift=_night(seeded))

    reasons = {row["staff_id"]: row["reason"] for row in selection.skipped}
    assert reasons[second] == SOURCE_SHIFT_TAKEN
    assert reasons[scene.staff[2]] == SOURCE_SHIFT_TAKEN
    assert not {item.staff_id for item in selection.items} & set(scene.staff)


def test_a_rejected_offer_does_not_take_the_source_shift(seeded: Session) -> None:
    scene, result, case = _movers(seeded)
    offer(seeded, case, _items(result)[scene.staff[0]], OutreachStatus.REJECTED)

    selection = wave_service.select_wave(seeded, case_id=case.id, shift=_night(seeded))

    assert scene.staff[0] not in {item.staff_id for item in selection.items}
    # The next person of the same source shift is still free to be offered
    reasons = {row["staff_id"]: row["reason"] for row in selection.skipped}
    assert reasons.get(scene.staff[1]) != SOURCE_SHIFT_TAKEN


def test_a_completed_move_takes_the_source_shift(seeded: Session) -> None:
    scene, result, case = _movers(seeded)
    first, second = scene.staff[:2]
    source_row = scene.row(first)
    source_row.status = RosterStatus.CANCELLED
    request = approval(seeded, case, _items(result)[first], approved=True)
    live = seeded.get(CandidateOutreach, request.outreach_id)
    assert live is not None
    live.status = OutreachStatus.CANCELLED
    seeded.add(
        RosterAssignment(
            staff_id=first,
            shift_id=_night(seeded).id,
            status=RosterStatus.ASSIGNED,
            assignment_type=AssignmentType.REPLACEMENT,
            candidate_source=CandidateSource.CROSS_WARD,
            transferred_from_assignment_id=source_row.id,
        )
    )
    seeded.flush()

    selection = wave_service.select_wave(seeded, case_id=case.id, shift=_night(seeded))

    reasons = {row["staff_id"]: row["reason"] for row in selection.skipped}
    assert reasons[second] == SOURCE_SHIFT_TAKEN
    assert not {item.staff_id for item in selection.items} & set(scene.staff)


def _move(db: Session, case: StaffingCase, item: CandidateItem, scene: Scene) -> None:
    """The first approval of `case` ends in a done move out of the source shift."""
    source_row = scene.row(item.staff_id)
    source_row.status = RosterStatus.CANCELLED
    request = approval(db, case, item, approved=True)
    live = db.get(CandidateOutreach, request.outreach_id)
    assert live is not None
    live.status = OutreachStatus.CANCELLED
    db.add(
        RosterAssignment(
            staff_id=item.staff_id,
            shift_id=item.proposed_shift_id,
            status=RosterStatus.ASSIGNED,
            assignment_type=AssignmentType.REPLACEMENT,
            candidate_source=CandidateSource.CROSS_WARD,
            transferred_from_assignment_id=source_row.id,
        )
    )
    db.flush()


def test_an_earlier_cases_move_does_not_take_the_source_shift_for_a_new_case(
    seeded: Session,
) -> None:
    scene, result, first_case = _movers(seeded)
    _move(seeded, first_case, _items(result)[scene.staff[0]], scene)
    first_case.status = CaseStatus.RESOLVED
    # Another absence opens a second case on the same destination shift
    leave(seeded, 104)
    second_case = make_case(seeded, CaseStatus.OPTIMIZING)
    record_gap(seeded, second_case)
    optimization_service.create_plan(seeded, second_case)

    selection = wave_service.select_wave(seeded, case_id=second_case.id, shift=_night(seeded))

    assert SOURCE_SHIFT_TAKEN not in {row["reason"] for row in selection.skipped}


def test_a_later_wave_keeps_the_person_who_fills_what_is_left_of_one_source_shift(
    seeded: Session,
) -> None:
    """A ranks first but cannot fill the ICU gap; B of the same source shift can."""
    scene = Scene(seeded, required=2, holders=3)
    # One ICU nurse more than the ward has: the open gap is 1 person, 1 RN and 1 ICU
    holders = {
        staff_id
        for staff_id in seeded.scalars(
            select(RosterAssignment.staff_id).where(
                RosterAssignment.shift_id == _night(seeded).id,
                RosterAssignment.status == RosterStatus.ASSIGNED,
                RosterAssignment.staff_id != 105,
            )
        )
        if seeded.get(StaffSkill, (staff_id, ICU)) is not None
    }
    requirement_skill = seeded.scalars(
        select(StaffingRequirementSkill)
        .join(
            StaffingRequirement,
            StaffingRequirement.id == StaffingRequirementSkill.staffing_requirement_id,
        )
        .where(
            StaffingRequirement.shift_id == _night(seeded).id,
            StaffingRequirementSkill.skill_id == ICU,
        )
    ).one()
    requirement_skill.required_count = len(holders) + 1
    seeded.flush()
    result = _plan(seeded)
    case = _case(seeded, result)
    items = _items(result)
    plain, icu = scene.staff[:2]
    _drop_skills(seeded, plain)
    seeded.add(StaffSkill(staff_id=plain, skill_id=BLS))
    seeded.flush()
    first, second = sorted((items[plain], items[icu]), key=lambda item: item.rank)
    if first.staff_id != plain:
        first.rank, second.rank = second.rank, first.rank
    # The first wave went out and nobody of it is left: this is a later wave
    for staff_id in (201, 202, 203):
        offer(seeded, case, items[staff_id], OutreachStatus.REJECTED)

    selection = wave_service.select_wave(seeded, case_id=case.id, shift=_night(seeded))

    chosen = {item.staff_id for item in selection.items}
    assert icu in chosen
    assert not chosen & {plain}


@pytest.mark.parametrize("overdue_by", [timedelta(0), timedelta(minutes=5)])
def test_an_overdue_offer_does_not_hold_the_source_shift(
    seeded: Session, overdue_by: timedelta
) -> None:
    scene, result, case = _movers(seeded)
    first, second = scene.staff[:2]
    sent = offer(seeded, case, _items(result)[first], OutreachStatus.SENT)
    sent.expires_at = clock.now() - overdue_by
    seeded.flush()

    selection = wave_service.select_wave(seeded, case_id=case.id, shift=_night(seeded))

    reasons = {row["staff_id"]: row["reason"] for row in selection.skipped}
    assert reasons.get(second) != SOURCE_SHIFT_TAKEN
    # The overdue offer is left as it is for the timeout job
    assert sent.status == OutreachStatus.SENT
