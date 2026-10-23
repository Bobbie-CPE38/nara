"""KPI of a test run (round 6 PR EV5a, docs/workflow.md 6.35.4)."""

from datetime import datetime, timedelta

from app.core import clock
from app.domain.enums import AuditAction
from app.services.test_run_kpi import Advance, Row, advanced_between, compute

START = datetime(2026, 10, 23, 21, 0, tzinfo=clock.APP_TIMEZONE)


def _at(seconds: float) -> datetime:
    return START + timedelta(seconds=seconds)


def _row(action: AuditAction, seconds: float, **payload: object) -> Row:
    return Row(action=action, at=_at(seconds), payload=dict(payload))


def _advance(before: float, seconds: float) -> Advance:
    return Advance(before=_at(before), after=_at(before + seconds), seconds=seconds)


FILLED = [
    _row(AuditAction.EVENT_RECEIVED, 0),
    _row(AuditAction.GAP_ASSESSED, 1),
    _row(AuditAction.SOLVER_EXECUTED, 2),
    _row(AuditAction.OFFER_SENT, 3),
    _row(AuditAction.OFFER_SENT, 3),
    _row(AuditAction.OFFER_ACCEPTED, 400),
    _row(AuditAction.APPROVAL_REQUESTED, 401),
    _row(AuditAction.APPROVAL_APPROVED, 431),
    _row(AuditAction.ASSIGNMENT_CREATED, 432),
]


def _kpi(rows: list[Row], advances: list[Advance], **kwargs: object) -> dict[str, object]:
    options: dict[str, object] = {
        "required_replacement_time": _at(7200),
        "skipped_by_plan": 3,
        "filled_from_other_ward": False,
    } | kwargs
    return compute(rows, advances, **options)  # type: ignore[arg-type]


def test_advances_inside_an_interval_are_taken_out() -> None:
    # Moved 300 s while waiting for the answer
    kpi = _kpi(FILLED, [_advance(50, 300)])

    assert kpi["time_to_fill_system_s"] == 432
    assert kpi["time_to_fill_s"] == 132
    assert kpi["first_accept_s"] == 97
    # Nothing was moved during detection or approval
    assert kpi["detect_s"] == 1 and kpi["approval_s"] == 30


def test_an_advance_outside_the_interval_is_not_taken_out() -> None:
    assert advanced_between([_advance(10, 60)], _at(100), _at(200)) == 0
    assert advanced_between([_advance(150, 60)], _at(100), _at(200)) == 0
    assert advanced_between([_advance(100, 60)], _at(100), _at(200)) == 60


def test_counts_and_flags() -> None:
    rows = [*FILLED, _row(AuditAction.SAFETY_FAILED, 420)]

    kpi = _kpi(rows, [], filled_from_other_ward=True)

    assert kpi["offers_sent"] == 2
    assert kpi["candidates_skipped_by_rules"] == 4
    assert kpi["filled_before_shift_start"] is True
    assert kpi["from_other_ward"] is True


def test_a_fill_after_the_required_time_is_late() -> None:
    kpi = _kpi(FILLED, [], required_replacement_time=_at(400))

    assert kpi["filled_before_shift_start"] is False


def test_what_did_not_happen_is_none_not_zero() -> None:
    rows = FILLED[:5]  # offers out, nobody answered

    kpi = _kpi(rows, [])

    assert kpi["first_offer_s"] == 3
    for name in ("first_accept_s", "approval_s", "time_to_fill_s", "time_to_fill_system_s"):
        assert kpi[name] is None
    assert kpi["filled_before_shift_start"] is None
    assert kpi["from_other_ward"] is None


def test_the_end_of_an_interval_is_after_its_start() -> None:
    """An OFFER_SENT of an earlier wave does not end an interval that starts later."""
    rows = [
        _row(AuditAction.OFFER_SENT, 0),
        _row(AuditAction.APPROVAL_APPROVED, 5),
        _row(AuditAction.APPROVAL_REQUESTED, 10),
        _row(AuditAction.APPROVAL_APPROVED, 40),
    ]

    assert _kpi(rows, [])["approval_s"] == 30
