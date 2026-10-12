"""orchestrator.recompute() against the seeded PostgreSQL (docs/workflow.md, section 5.3).

The handlers are stubs: OUTREACH goes to WAITING_RESPONSE and EXECUTING to RESOLVED.
What is real here is the status computed from the rows of the case.
"""

from unittest import mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Role, StaffingCase
from app.domain.enums import (
    AUTOMATION_STOPPED_STATUSES,
    WAITING_CASE_STATUSES,
    AuditAction,
    CaseStatus,
    OutreachStatus,
)
from app.domain.errors import CaseNotFoundError
from app.domain.workflow.transitions import InvalidTransitionError
from app.workflow import orchestrator
from app.workflow.handlers.base import HandlerResult
from tests.integration.case_rows import (
    DAY_SHIFT,
    approval,
    assign,
    make_case,
    make_plan,
    offer,
    short_case,
)
from tests.integration.conftest import returns

pytestmark = pytest.mark.usefixtures("stub_handlers")

WAITING_RESPONSE = CaseStatus.WAITING_RESPONSE
WAITING_APPROVAL = CaseStatus.WAITING_APPROVAL


def _audit(db: Session, case: StaffingCase) -> list[AuditLog]:
    return list(
        db.scalars(select(AuditLog).where(AuditLog.case_id == case.id).order_by(AuditLog.id))
    )


def _status_changes(db: Session, case: StaffingCase) -> list[tuple[str, str]]:
    return [
        (row.payload["from"], row.payload["to"])
        for row in _audit(db, case)
        if row.action is AuditAction.CASE_STATUS_CHANGED
    ]


def _status(db: Session, case: StaffingCase) -> CaseStatus:
    db.expire_all()
    return case.status


class Counting:
    """A handler that counts its calls and then returns a fixed result."""

    def __init__(self, **result: object) -> None:
        self.calls = 0
        self._handler = returns(**result)

    def __call__(self, db: Session, case: StaffingCase) -> HandlerResult:
        self.calls += 1
        return self._handler(db, case)


# --------------------------------------------------------------------------- #
# Cases recompute leaves alone
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", sorted(AUTOMATION_STOPPED_STATUSES))
def test_a_stopped_case_is_not_touched(seeded: Session, status: CaseStatus) -> None:
    """Even with rows that would call for another status: a stopped case has no way out."""
    case, items = short_case(seeded, status=status)
    assign(seeded, case, items[201])

    result = orchestrator.recompute(seeded, case.id)

    assert result is status
    assert _status(seeded, case) is status
    assert _audit(seeded, case) == []


def test_a_stopped_case_without_a_gap_row_is_still_left_alone(seeded: Session) -> None:
    """Nothing is loaded for a stopped case, so its missing rows cannot fail it again."""
    case = make_case(seeded, CaseStatus.FAILED)

    assert orchestrator.recompute(seeded, case.id) is CaseStatus.FAILED
    assert _audit(seeded, case) == []


def test_recompute_on_a_stopped_case_commits_the_callers_work_once(seeded: Session) -> None:
    """The timeout job marks an offer of a FAILED case and then calls recompute."""
    case, items = short_case(seeded, status=CaseStatus.FAILED)
    sent = offer(seeded, case, items[201])
    sent.status = OutreachStatus.TIMEOUT

    with mock.patch.object(seeded, "commit", wraps=seeded.commit) as commit:
        orchestrator.recompute(seeded, case.id)

    assert commit.call_count == 1
    seeded.expire_all()
    assert sent.status is OutreachStatus.TIMEOUT


@pytest.mark.parametrize(
    "status",
    sorted(set(CaseStatus) - WAITING_CASE_STATUSES - AUTOMATION_STOPPED_STATUSES),
)
def test_a_case_that_is_not_waiting_is_rejected_without_touching_it(
    seeded: Session, status: CaseStatus
) -> None:
    case, _ = short_case(seeded, status=status)

    with pytest.raises(InvalidTransitionError, match="not at a wait point"):
        orchestrator.recompute(seeded, case.id)

    assert _status(seeded, case) is status
    assert _audit(seeded, case) == []


def test_unknown_case_raises(seeded: Session) -> None:
    with pytest.raises(CaseNotFoundError, match="999999"):
        orchestrator.recompute(seeded, 999_999)


# --------------------------------------------------------------------------- #
# Same status: nothing is written
# --------------------------------------------------------------------------- #
def test_waiting_response_with_an_open_offer_stays(seeded: Session) -> None:
    case, items = short_case(seeded)
    offer(seeded, case, items[201])

    with mock.patch.object(seeded, "commit", wraps=seeded.commit) as commit:
        result = orchestrator.recompute(seeded, case.id)

    assert result is WAITING_RESPONSE
    assert _audit(seeded, case) == []
    assert commit.call_count == 1


def test_waiting_approval_with_the_approval_still_pending_stays(seeded: Session) -> None:
    case, items = short_case(seeded, status=WAITING_APPROVAL)
    approval(seeded, case, items[201])

    assert orchestrator.recompute(seeded, case.id) is WAITING_APPROVAL
    assert _audit(seeded, case) == []


def test_recompute_twice_gives_the_same_result(seeded: Session) -> None:
    case, items = short_case(seeded)
    approval(seeded, case, items[201])

    assert orchestrator.recompute(seeded, case.id) is WAITING_APPROVAL
    assert orchestrator.recompute(seeded, case.id) is WAITING_APPROVAL
    assert _status_changes(seeded, case) == [("WAITING_RESPONSE", "WAITING_APPROVAL")]


# --------------------------------------------------------------------------- #
# The five moves out of a wait point
# --------------------------------------------------------------------------- #
def test_t1_no_open_offer_sends_the_next_wave(seeded: Session) -> None:
    """Both candidates of the wave rejected: the case goes back through OUTREACH."""
    case, items = short_case(seeded)
    offer(seeded, case, items[201], OutreachStatus.REJECTED)
    offer(seeded, case, items[202], OutreachStatus.REJECTED)

    result = orchestrator.recompute(seeded, case.id)

    assert result is WAITING_RESPONSE
    assert _status_changes(seeded, case) == [
        ("WAITING_RESPONSE", "OUTREACH"),
        ("OUTREACH", "WAITING_RESPONSE"),
    ]


def test_t2_a_pending_approval_that_covers_the_gap_waits_for_the_approver(
    seeded: Session,
) -> None:
    """201 accepted and passed Safety. The offer of 202 stays open, but is not needed."""
    case, items = short_case(seeded)
    offer(seeded, case, items[201], OutreachStatus.ACCEPTED)
    approval(seeded, case, items[201])
    offer(seeded, case, items[202])

    assert orchestrator.recompute(seeded, case.id) is WAITING_APPROVAL
    assert _status_changes(seeded, case) == [("WAITING_RESPONSE", "WAITING_APPROVAL")]


def test_t3_a_rejected_approval_falls_back_to_the_open_offer(seeded: Session) -> None:
    case, items = short_case(seeded, status=WAITING_APPROVAL)
    offer(seeded, case, items[201], OutreachStatus.CANCELLED)
    approval(seeded, case, items[201], approved=False)
    offer(seeded, case, items[202])

    assert orchestrator.recompute(seeded, case.id) is WAITING_RESPONSE
    assert _status_changes(seeded, case) == [("WAITING_APPROVAL", "WAITING_RESPONSE")]


def test_t4_a_rejected_approval_with_no_open_offer_sends_the_next_wave(
    seeded: Session,
) -> None:
    case, items = short_case(seeded, status=WAITING_APPROVAL)
    offer(seeded, case, items[201], OutreachStatus.CANCELLED)
    approval(seeded, case, items[201], approved=False)
    offer(seeded, case, items[202], OutreachStatus.REJECTED)

    assert orchestrator.recompute(seeded, case.id) is WAITING_RESPONSE
    assert _status_changes(seeded, case) == [
        ("WAITING_APPROVAL", "OUTREACH"),
        ("OUTREACH", "WAITING_RESPONSE"),
    ]


def test_assigned_staff_closing_the_gap_resolves_the_case(seeded: Session) -> None:
    case, items = short_case(seeded, status=WAITING_APPROVAL)
    offer(seeded, case, items[201], OutreachStatus.ACCEPTED)
    assign(seeded, case, items[201])

    with mock.patch.object(seeded, "commit", wraps=seeded.commit) as commit:
        result = orchestrator.recompute(seeded, case.id)

    assert result is CaseStatus.RESOLVED
    assert commit.call_count == 1
    assert _status_changes(seeded, case) == [
        ("WAITING_APPROVAL", "EXECUTING"),
        ("EXECUTING", "RESOLVED"),
    ]


def test_first_of_two_approvals_does_not_move_the_case(seeded: Session) -> None:
    """Gap of two: 201 is on the roster, 202 still waits for the approver (Q27)."""
    case, items = short_case(seeded, 104, 105, status=WAITING_APPROVAL)
    assign(seeded, case, items[201])
    approval(seeded, case, items[202])

    assert orchestrator.recompute(seeded, case.id) is WAITING_APPROVAL
    assert _audit(seeded, case) == []


def test_paused_offer_is_not_an_open_offer_so_the_next_wave_goes_out(seeded: Session) -> None:
    """201 accepted another case: this case does not wait for 201 (Q29)."""
    case, items = short_case(seeded)
    offer(seeded, case, items[201])
    other = make_case(seeded, WAITING_APPROVAL, shift_id=DAY_SHIFT)
    offer(seeded, other, make_plan(seeded, other, (201,))[201], OutreachStatus.ACCEPTED)

    orchestrator.recompute(seeded, case.id)

    assert _status_changes(seeded, case)[0] == ("WAITING_RESPONSE", "OUTREACH")


# --------------------------------------------------------------------------- #
# OUTREACH ends the round in one of three ways and never loops (T5, T7)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("next_status", "wait"),
    [
        (CaseStatus.WAITING_RESPONSE, True),
        (CaseStatus.WAITING_APPROVAL, True),  # T7
        (CaseStatus.MANUAL_HANDOFF, False),  # T5
    ],
)
@pytest.mark.parametrize("start", sorted(WAITING_CASE_STATUSES))
def test_re_entering_outreach_runs_the_handler_once_and_stops(
    seeded: Session,
    monkeypatch: pytest.MonkeyPatch,
    start: CaseStatus,
    next_status: CaseStatus,
    wait: bool,
) -> None:
    """T1 and T4 lead into OUTREACH, and every exit of OUTREACH is a wait point or a stop."""
    case, _ = short_case(seeded, status=start)
    contact = Counting(next_status=next_status, wait=wait)
    monkeypatch.setitem(orchestrator.HANDLERS, CaseStatus.OUTREACH, contact)

    result = orchestrator.recompute(seeded, case.id)

    assert contact.calls == 1
    assert result is next_status
    assert _status_changes(seeded, case) == [
        (start.value, "OUTREACH"),
        ("OUTREACH", next_status.value),
    ]
    assert not any(row.action is AuditAction.WORKFLOW_FAILED for row in _audit(seeded, case))


def test_manual_handoff_from_a_handler_stops_the_round_without_waiting(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T6: the handler returns MANUAL_HANDOFF with wait=False and no later handler runs."""
    case = make_case(seeded, CaseStatus.OPTIMIZING)
    contact = Counting(next_status=CaseStatus.WAITING_RESPONSE, wait=True)
    monkeypatch.setitem(
        orchestrator.HANDLERS,
        CaseStatus.OPTIMIZING,
        returns(next_status=CaseStatus.MANUAL_HANDOFF),
    )
    monkeypatch.setitem(orchestrator.HANDLERS, CaseStatus.OUTREACH, contact)

    orchestrator.advance(seeded, case.id)

    assert _status(seeded, case) is CaseStatus.MANUAL_HANDOFF
    assert contact.calls == 0
    assert _status_changes(seeded, case) == [("OPTIMIZING", "MANUAL_HANDOFF")]


def test_manual_handoff_with_wait_true_breaks_the_handler_contract(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MANUAL_HANDOFF is not a wait point, so wait=True fails the case (section 6.1)."""
    case, _ = short_case(seeded)
    monkeypatch.setitem(
        orchestrator.HANDLERS,
        CaseStatus.OUTREACH,
        returns(next_status=CaseStatus.MANUAL_HANDOFF, wait=True),
    )

    assert orchestrator.recompute(seeded, case.id) is CaseStatus.FAILED


def test_a_case_in_manual_handoff_is_then_left_alone(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, items = short_case(seeded)
    monkeypatch.setitem(
        orchestrator.HANDLERS, CaseStatus.OUTREACH, returns(next_status=CaseStatus.MANUAL_HANDOFF)
    )
    assert orchestrator.recompute(seeded, case.id) is CaseStatus.MANUAL_HANDOFF
    before = len(_audit(seeded, case))

    approval(seeded, case, items[201])

    assert orchestrator.recompute(seeded, case.id) is CaseStatus.MANUAL_HANDOFF
    assert len(_audit(seeded, case)) == before


# --------------------------------------------------------------------------- #
# D11: a failure while computing or while running the round
# --------------------------------------------------------------------------- #
def test_missing_gap_row_fails_the_case_and_keeps_the_callers_work(seeded: Session) -> None:
    case = make_case(seeded)
    seeded.add(Role(name="WRITTEN_BY_THE_CALLER"))

    result = orchestrator.recompute(seeded, case.id)

    assert result is CaseStatus.FAILED
    assert _status_changes(seeded, case) == [("WAITING_RESPONSE", "FAILED")]
    failure = _audit(seeded, case)[-1]
    assert failure.action is AuditAction.WORKFLOW_FAILED
    assert failure.payload == {
        "from": "WAITING_RESPONSE",
        "failed_at": "WAITING_RESPONSE",
        "error_type": "GapNotFoundError",
    }
    assert seeded.scalar(select(Role).where(Role.name == "WRITTEN_BY_THE_CALLER")) is not None


def test_a_computed_move_the_table_does_not_allow_fails_the_case(seeded: Session) -> None:
    """WAITING_RESPONSE has no edge to EXECUTING: reaching this means a step was skipped."""
    case, items = short_case(seeded)
    assign(seeded, case, items[201])

    result = orchestrator.recompute(seeded, case.id)

    assert result is CaseStatus.FAILED
    assert _audit(seeded, case)[-1].payload == {
        "from": "WAITING_RESPONSE",
        "failed_at": "WAITING_RESPONSE",
        "error_type": "InvalidTransitionError",
    }


def test_handler_failure_after_the_computed_move_rolls_the_move_back(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    case, _ = short_case(seeded)

    def failing_contact(db: Session, case: StaffingCase) -> HandlerResult:
        db.add(Role(name="WRITTEN_BEFORE_THE_ERROR"))
        db.flush()
        raise RuntimeError("line is down")

    monkeypatch.setitem(orchestrator.HANDLERS, CaseStatus.OUTREACH, failing_contact)

    with mock.patch.object(seeded, "commit", wraps=seeded.commit) as commit:
        result = orchestrator.recompute(seeded, case.id)

    assert commit.call_count == 1
    assert result is CaseStatus.FAILED
    # The move to OUTREACH was undone with the round: the failure starts at the wait point
    assert _status_changes(seeded, case) == [("WAITING_RESPONSE", "FAILED")]
    assert _audit(seeded, case)[-1].payload == {
        "from": "WAITING_RESPONSE",
        "failed_at": "OUTREACH",
        "error_type": "RuntimeError",
    }
    assert seeded.scalar(select(Role).where(Role.name == "WRITTEN_BEFORE_THE_ERROR")) is None


def test_recompute_flushes_the_callers_pending_rows_before_reading(
    production_seeded: Session,
) -> None:
    """Autoflush is off in production: an unflushed approval must still be counted."""
    db = production_seeded
    case, items = short_case(db)
    request = approval(db, case, items[201], approved=False)
    # The caller reopens the request and has not flushed yet
    request.is_pending, request.is_approved = True, None

    assert orchestrator.recompute(db, case.id) is WAITING_APPROVAL
