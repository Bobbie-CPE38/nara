from collections.abc import Callable
from unittest.mock import create_autospec

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models.staffing_case import StaffingCase
from app.domain.enums import CaseStatus
from app.domain.workflow.transitions import assert_transition
from app.workflow.handlers import (
    assess_staffing,
    intake_event,
    optimize,
    validate_safety,
)
from app.workflow.handlers.base import HandlerResult


@pytest.mark.parametrize(
    ("handler", "current", "next_status", "wait"),
    [
        (intake_event.handle, CaseStatus.OPEN, CaseStatus.ASSESSING, False),
        (assess_staffing.handle, CaseStatus.ASSESSING, CaseStatus.OPTIMIZING, False),
        (optimize.handle, CaseStatus.OPTIMIZING, CaseStatus.OUTREACH, False),
        (validate_safety.handle, CaseStatus.SAFETY_VALIDATION, CaseStatus.WAITING_APPROVAL, True),
    ],
)
def test_stub_preserves_case_and_transaction_ownership(
    handler: Callable[[Session, StaffingCase], HandlerResult],
    current: CaseStatus,
    next_status: CaseStatus,
    wait: bool,
) -> None:
    db = create_autospec(Session, instance=True)
    case = StaffingCase(
        id=1,
        event_id=1,
        shift_id=1,
        status=current,
        required_replacement_time=clock.now(),
    )
    original = dict(vars(case))
    result = handler(db, case)
    assert result.next_status is next_status
    assert result.wait is wait
    assert_transition(current, result.next_status)
    assert vars(case) == original
    assert db.mock_calls == []


def test_handler_result_defaults_to_continuing() -> None:
    result = HandlerResult(next_status=CaseStatus.ASSESSING)
    assert result.wait is False


def test_handler_result_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        HandlerResult.model_validate({"next_status": "NOT_A_CASE_STATUS"})
