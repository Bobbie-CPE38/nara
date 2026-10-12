"""hard_rule_service against the seeded PostgreSQL (round 1 contract, sections 7.2 and 7.3)."""

from unittest.mock import patch

import pytest
from sqlalchemy import delete
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.db.models import CandidateItemTarget, Shift, StaffingRequirementRole
from app.domain.constraints.codes import HardRuleCode
from app.domain.enums import SelectionType, TargetType
from app.services import hard_rule_service
from tests.integration.case_rows import NIGHT_SHIFT, cancel_roster, leave, make_case, make_plan

ON_SHIFT = (101, 102, 103, 104, 105)
ALL_STAFF = (*ON_SHIFT, 201, 202, 203, 900)


def _night(db: Session) -> Shift:
    shift = db.get(Shift, NIGHT_SHIFT)
    assert shift is not None
    return shift


def _failed(checks: dict[int, hard_rule_service.CandidateCheck]) -> dict[int, tuple[str, ...]]:
    return {
        key: tuple(rule.value for rule in check.result.failed_rules)
        for key, check in checks.items()
    }


def test_every_staff_member_of_the_golden_case_after_a_leave(seeded: Session) -> None:
    leave(seeded, 105)

    checks = hard_rule_service.check_staff(seeded, shift=_night(seeded), staff_ids=ALL_STAFF)

    failed = _failed(checks)
    for staff_id in (101, 102, 103, 104):
        assert failed[staff_id] == ("ALREADY_ON_SHIFT",)
    assert failed[105] == ("UNAVAILABLE",)
    for staff_id in (201, 202, 203):
        assert failed[staff_id] == ()
    assert failed[900] == ("ROLE_MISMATCH",)


def test_the_roster_of_a_candidate_is_part_of_the_check(seeded: Session) -> None:
    check = hard_rule_service.check_staff(seeded, shift=_night(seeded), staff_ids=[202])[202]

    assert any(entry.shift.shift_id == 2 for entry in check.context.roster)
    assert check.result.details["weekly_hours"] == 16
    assert check.result.details["projected_consecutive_shifts"] == 2


def test_a_cancelled_roster_row_does_not_block(seeded: Session) -> None:
    cancel_roster(seeded, 105)

    checks = hard_rule_service.check_staff(seeded, shift=_night(seeded), staff_ids=[105])

    assert _failed(checks) == {105: ()}


def test_a_requirement_without_roles_lets_any_role_pass(seeded: Session) -> None:
    seeded.execute(
        delete(StaffingRequirementRole).where(StaffingRequirementRole.staffing_requirement_id == 1)
    )
    seeded.flush()

    checks = hard_rule_service.check_staff(seeded, shift=_night(seeded), staff_ids=[900])

    assert _failed(checks) == {900: ()}


def test_check_items_reads_the_target_rows(seeded: Session) -> None:
    case = make_case(seeded)
    items = make_plan(seeded, case)
    shift = _night(seeded)
    ordered = list(items.values())

    before = hard_rule_service.check_items(seeded, shift=shift, items=ordered)
    assert _failed(before) == {item.id: () for item in ordered}

    seeded.add_all(
        [
            CandidateItemTarget(
                candidate_item_id=items[202].id,
                target_type=TargetType.SKILL,
                skill_id=1,
                selection_type=SelectionType.PRIMARY,
            ),
            CandidateItemTarget(
                candidate_item_id=items[203].id,
                target_type=TargetType.SKILL,
                skill_id=1,
                selection_type=SelectionType.PRIMARY,
            ),
            CandidateItemTarget(
                candidate_item_id=items[201].id,
                target_type=TargetType.ROLE,
                role_id=2,
                selection_type=SelectionType.PRIMARY,
            ),
        ]
    )
    seeded.flush()

    after = hard_rule_service.check_items(seeded, shift=shift, items=ordered)

    failed = _failed(after)
    assert failed[items[202].id] == (HardRuleCode.SKILL_MISMATCH.value,)
    assert failed[items[203].id] == ()
    assert failed[items[201].id] == (HardRuleCode.ROLE_MISMATCH.value,)


def test_check_items_rejects_an_item_of_another_shift(seeded: Session) -> None:
    case = make_case(seeded)
    items = make_plan(seeded, case)
    other = seeded.get(Shift, 2)
    assert other is not None

    with pytest.raises(ValueError):
        hard_rule_service.check_items(seeded, shift=other, items=[items[201]])


def test_an_unknown_staff_member_raises(seeded: Session) -> None:
    with pytest.raises(LookupError):
        hard_rule_service.check_staff(seeded, shift=_night(seeded), staff_ids=[999])


def test_checking_is_read_only(production_seeded: Session) -> None:
    db = production_seeded
    shift = _night(db)
    with (
        patch.object(db, "flush", side_effect=AssertionError("read flushed")),
        patch.object(db, "commit", side_effect=AssertionError("read committed")),
    ):
        hard_rule_service.check_staff(db, shift=shift, staff_ids=[201])


def test_lock_staff_locks_in_one_statement_and_skips_an_empty_list(seeded: Session) -> None:
    with patch.object(seeded, "execute", wraps=seeded.execute) as execute:
        hard_rule_service.lock_staff(seeded, [])
        assert execute.call_count == 0
        hard_rule_service.lock_staff(seeded, [202, 201])

    [call] = execute.call_args_list
    assert "FOR NO KEY UPDATE" in str(call.args[0].compile(dialect=postgresql.dialect()))
