"""Scenario soft_constraint: equal Hard Rule results, different first waves (contract 8.3)."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    CandidateItem,
    CandidateItemTarget,
    CandidatePlan,
    StaffWorkingTimeSnapshot,
)
from app.domain.enums import CaseStatus
from app.seed.scenarios import soft_constraint
from app.workflow.handlers import optimize
from tests.integration.case_rows import leave, make_case, record_gap
from tests.integration.conftest import DEMO_NOW


def _plan(db: Session) -> tuple[CandidatePlan, list[CandidateItem]]:
    leave(db, 105)
    case = make_case(db, CaseStatus.OPTIMIZING)
    record_gap(db, case)
    optimize.handle(db, case)
    plan = db.scalars(select(CandidatePlan).where(CandidatePlan.case_id == case.id)).one()
    items = list(
        db.scalars(
            select(CandidateItem)
            .where(CandidateItem.plan_id == plan.id)
            .order_by(CandidateItem.rank)
        )
    )
    return plan, items


def _targeted(db: Session, items: list[CandidateItem]) -> set[int]:
    ids = set(
        db.scalars(
            select(CandidateItemTarget.candidate_item_id).where(
                CandidateItemTarget.candidate_item_id.in_([item.id for item in items])
            )
        )
    )
    return {item.staff_id for item in items if item.id in ids}


def test_seeded_weights_prefer_the_rested_staff(seeded: Session) -> None:
    soft_constraint.seed(seeded)

    plan, items = _plan(seeded)

    assert [item.staff_id for item in items] == [202, 203, 201]
    assert _targeted(seeded, items) == {202, 203}
    assert plan.objective_score == 20400
    busy = next(item for item in items if item.staff_id == 201)
    assert busy.working_time_snapshot_id is not None
    snapshot = seeded.get(StaffWorkingTimeSnapshot, busy.working_time_snapshot_id)
    assert snapshot is not None
    assert snapshot.hours_this_week == 24
    assert snapshot.rest_hours == 54
    assert snapshot.consecutive_shifts == 0


def test_without_the_workload_weight_rank_still_follows_ranking_key(seeded: Session) -> None:
    soft_constraint.seed(seeded)
    soft_constraint.ignore_workload(seeded)

    plan, items = _plan(seeded)

    assert [item.staff_id for item in items] == [202, 201, 203]
    assert _targeted(seeded, items) == {201, 202}
    assert plan.objective_score == 20060


def test_the_scenario_needs_thursday_or_later(seeded: Session) -> None:
    # DEMO_NOW is a Friday: three days earlier is a Tuesday
    clock.set_time(DEMO_NOW - timedelta(days=3))
    with pytest.raises(ValueError, match="Thursday"):
        soft_constraint.seed(seeded)
