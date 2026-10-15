"""Roster rows of ended shifts become COMPLETED (round 3 PR R, docs/workflow.md 3.8).

The seeded night shift (1) runs 2026-10-09 23:00 to 2026-10-10 07:00 with 101 to
105 on it; the day shift (2) runs 2026-10-11 07:00 to 15:00 with 202 and 203.
COMPLETED must count like ASSIGNED everywhere, so completing a shift moves no
gap, fatigue check or working time.
"""

from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import RosterAssignment, Shift, StaffingRequirement
from app.db.session import SessionLocal
from app.domain.constraints.codes import HardRuleCode
from app.domain.enums import RosterStatus, ShiftType
from app.seed import load
from app.services import (
    gap_service,
    hard_rule_service,
    job_service,
    roster_completion_service,
    working_time_service,
)
from tests.integration.case_rows import DAY_SHIFT, NIGHT_SHIFT, cancel_roster
from tests.integration.conftest import DEMO_NOW

NIGHT_END = DEMO_NOW + timedelta(hours=10)  # 2026-10-10 07:00


def statuses(db: Session, shift_id: int) -> dict[int, RosterStatus]:
    db.expire_all()
    return {
        row.staff_id: row.status
        for row in db.scalars(select(RosterAssignment).where(RosterAssignment.shift_id == shift_id))
    }


def test_only_assigned_rows_of_ended_shifts_become_completed(production_seeded: Session) -> None:
    db = production_seeded
    cancel_roster(db, 105)
    db.commit()

    clock.set_time(NIGHT_END)
    completed = roster_completion_service.complete_ended_shifts(db)

    night = statuses(db, NIGHT_SHIFT)
    assert {staff_id for staff_id, status in night.items() if status is RosterStatus.COMPLETED} == {
        101,
        102,
        103,
        104,
    }
    assert night[105] is RosterStatus.CANCELLED
    assert set(statuses(db, DAY_SHIFT).values()) == {RosterStatus.ASSIGNED}
    # Every ended shift: the Medicine night of the seed ends with the ICU night
    assert completed == sorted(
        db.scalars(
            select(RosterAssignment.id).where(RosterAssignment.status == RosterStatus.COMPLETED)
        )
    )
    # Nothing left to do on the next tick
    assert roster_completion_service.complete_ended_shifts(db) == []


def test_a_running_shift_is_not_completed(production_seeded: Session) -> None:
    db = production_seeded
    clock.set_time(NIGHT_END - timedelta(seconds=1))

    assert roster_completion_service.complete_ended_shifts(db) == []
    assert set(statuses(db, NIGHT_SHIFT).values()) == {RosterStatus.ASSIGNED}


def test_the_job_tick_completes_ended_shifts(production_seeded: Session) -> None:
    db = production_seeded
    clock.set_time(NIGHT_END)

    work = job_service.run_due_work(db)

    # Five on the ICU night and five on the Medicine night of the seed
    assert len(work.completed_assignment_ids) == 10
    assert set(statuses(db, NIGHT_SHIFT).values()) == {RosterStatus.COMPLETED}


def test_completing_a_shift_moves_no_gap_fatigue_check_or_working_time(
    production_seeded: Session,
) -> None:
    """The silent break this guards: yesterday's shift dropping out of the counts."""
    db = production_seeded
    cancel_roster(db, 105)
    # Starts the moment the night shift ends: no rest for anyone who worked it
    morning = Shift(
        ward_id=1,
        patient_count=2,
        start_at=NIGHT_END,
        end_at=NIGHT_END + timedelta(hours=8),
        shift_type=ShiftType.DAY,
        is_active=True,
    )
    db.add(morning)
    db.flush()
    db.add(
        StaffingRequirement(
            shift_id=morning.id, required_staff=1, minimum_staff=1, created_at=DEMO_NOW
        )
    )
    db.commit()
    night = db.get(Shift, NIGHT_SHIFT)
    assert night is not None
    clock.set_time(NIGHT_END)

    def counts() -> tuple[object, ...]:
        db.expire_all()
        checks = hard_rule_service.check_staff(db, shift=morning, staff_ids=[101])
        captured = working_time_service.capture(db, [101], captured_at=NIGHT_END)
        values = captured[101].values
        db.rollback()
        return (
            gap_service.assess_shift(db, night).result,
            checks[101].result.failed_rules,
            checks[101].result.details,
            values.hours_this_week,
            values.overtime_hours,
        )

    before = counts()
    assert HardRuleCode.INSUFFICIENT_REST in before[1]

    roster_completion_service.complete_ended_shifts(db)

    assert statuses(db, NIGHT_SHIFT)[101] is RosterStatus.COMPLETED
    assert counts() == before


# --------------------------------------------------------------------------- #
# Two connections: a row another transaction holds is skipped, not waited on
# --------------------------------------------------------------------------- #
def test_a_row_held_by_another_transaction_is_left_for_the_next_tick(
    frozen_clock: datetime, restore_empty_database: None
) -> None:
    with SessionLocal.begin() as db:
        load(db)
        held_id = db.scalars(
            select(RosterAssignment.id).where(
                RosterAssignment.staff_id == 101, RosterAssignment.shift_id == NIGHT_SHIFT
            )
        ).one()
    clock.set_time(NIGHT_END)

    with SessionLocal() as holder, SessionLocal() as job:
        # What a leave report does to the row before it cancels it
        holder.execute(
            select(RosterAssignment).where(RosterAssignment.id == held_id).with_for_update()
        )
        # Without SKIP LOCKED this would wait and fail on the timeout
        job.execute(text("SET lock_timeout = '2s'"))
        first = roster_completion_service.complete_ended_shifts(job)
        holder.rollback()
        second = roster_completion_service.complete_ended_shifts(job)

    # Four ICU and five Medicine rows
    assert held_id not in first and len(first) == 9
    assert second == [held_id]
