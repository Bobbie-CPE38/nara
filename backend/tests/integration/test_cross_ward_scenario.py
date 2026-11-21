"""The cross_ward test-run scenario plans only cross-ward people (round 6 PR EV5a, 6.35.3).

A row of the silent-failure table of 6.35.6: if a later seed change gives ICU a
safe nurse again, or leaves Medicine at its target, the scenario stops testing
the two-ward path without any other test failing.
"""

from app.domain.constraints.codes import HardRuleCode
from app.domain.enums import ApprovalSide, CandidateSource, CaseStatus
from app.seed.scenarios import cross_ward
from app.seed.scenarios.multi_ward import MEDICINE_WARD
from app.services import approval_wards, optimization_service
from tests.integration.case_rows import leave, make_case, record_gap


def _plan(db):
    cross_ward.seed(db)
    db.flush()
    leave(db, 105)
    case = make_case(db, CaseStatus.OPTIMIZING)
    record_gap(db, case)
    return optimization_service.create_plan(db, case)


def test_every_candidate_comes_from_medicine_and_needs_both_wards(production_seeded):
    result = _plan(production_seeded)

    assert result.items, "the scenario must leave a safe candidate"
    assert {item.source for item in result.items} <= {
        CandidateSource.CROSS_WARD,
        CandidateSource.FLOAT_POOL,
    }
    assert any(item.source == CandidateSource.CROSS_WARD for item in result.items)
    assert cross_ward.EXTRA_MEDICINE_RN in {item.staff_id for item in result.items}
    for item in result.items:
        assert approval_wards.required_wards(production_seeded, item) == {
            ApprovalSide.DESTINATION: cross_ward.ICU_WARD,
            ApprovalSide.SOURCE: MEDICINE_WARD,
        }


def test_free_icu_nurses_fail_on_rest(production_seeded):
    result = _plan(production_seeded)

    reasons = {skipped.staff_id: skipped.reason for skipped in result.skipped}
    for staff_id in cross_ward.TIRED_NURSES:
        assert reasons[staff_id] == HardRuleCode.INSUFFICIENT_REST


def test_golden_case_alone_still_plans_icu_nurses(production_seeded):
    """Without the scenario the Golden Case is unchanged: the guard against a leaky seed."""
    leave(production_seeded, 105)
    case = make_case(production_seeded, CaseStatus.OPTIMIZING)
    record_gap(production_seeded, case)
    result = optimization_service.create_plan(production_seeded, case)

    assert {item.source for item in result.items} == {CandidateSource.SAME_WARD}
