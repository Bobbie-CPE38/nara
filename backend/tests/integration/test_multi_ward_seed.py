"""The multi-ward demo data (round 4 PR W4, docs/workflow.md 6.19, 6.21).

The Golden Case must plan as it did with one ward (R4-Q38), so nobody of another
ward may reach the pool of an ICU shift, not even to be skipped.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import HEAD_NURSE_ROLE, SUPERVISOR_ROLE
from app.db.models import Role, RosterAssignment, Shift, Staff, Ward
from app.domain.enums import CaseStatus
from app.seed.scenarios.multi_ward import FLOAT_POOL_WARD, MEDICINE_WARD, MIRRORED_SHIFTS
from app.services import optimization_service
from tests.integration.case_rows import leave, make_case, record_gap

pytestmark = pytest.mark.usefixtures("frozen_clock")


def test_wards_roles_and_people(seeded: Session) -> None:
    wards = {ward.id: ward for ward in seeded.scalars(select(Ward))}
    assert {ward_id: (w.name, w.is_active, w.is_float_pool) for ward_id, w in wards.items()} == {
        1: ("ICU", True, False),
        MEDICINE_WARD: ("Medicine", True, False),
        FLOAT_POOL_WARD: ("Float Pool", True, True),
    }
    roles = {role.name: role.id for role in seeded.scalars(select(Role))}
    assert SUPERVISOR_ROLE in roles

    def heads(ward_id: int) -> set[int]:
        return set(
            seeded.scalars(
                select(Staff.id).where(
                    Staff.home_ward_id == ward_id, Staff.role_id == roles[HEAD_NURSE_ROLE]
                )
            )
        )

    assert heads(1) == {900}
    assert heads(MEDICINE_WARD) == {902}
    assert set(seeded.scalars(select(Staff.id).where(Staff.role_id == roles[SUPERVISOR_ROLE]))) == {
        950
    }
    float_rns = set(seeded.scalars(select(Staff.id).where(Staff.home_ward_id == FLOAT_POOL_WARD)))
    assert float_rns == {401}


def test_the_float_pool_has_no_shifts_and_medicine_mirrors_icu(seeded: Session) -> None:
    assert seeded.scalars(select(Shift).where(Shift.ward_id == FLOAT_POOL_WARD)).all() == []
    for shift_id, icu_id in MIRRORED_SHIFTS.items():
        medicine, icu = seeded.get(Shift, shift_id), seeded.get(Shift, icu_id)
        assert medicine is not None and icu is not None
        assert medicine.ward_id == MEDICINE_WARD
        assert (medicine.start_at, medicine.end_at) == (icu.start_at, icu.end_at)
        on_duty = set(
            seeded.scalars(
                select(RosterAssignment.staff_id).where(RosterAssignment.shift_id == shift_id)
            )
        )
        assert on_duty == {301, 302, 401, 902, 950}


@pytest.mark.parametrize("shift_id", [1, 2])
def test_no_one_of_another_ward_reaches_an_icu_pool(seeded: Session, shift_id: int) -> None:
    leave(seeded, 105 if shift_id == 1 else 203, shift_id)
    case = make_case(seeded, CaseStatus.OPTIMIZING, shift_id=shift_id)
    record_gap(seeded, case)

    result = optimization_service.create_plan(seeded, case)

    planned = {item.staff_id for item in result.items} | {row.staff_id for row in result.skipped}
    icu = set(seeded.scalars(select(Staff.id).where(Staff.home_ward_id == 1)))
    assert planned <= icu
    # Not vacuous: the ICU people are still planned or skipped with a code
    assert {201, 202, 203} <= planned
