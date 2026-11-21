"""Bodies of the test-run routes (round 6 PR EV5a, docs/workflow.md 6.35.2)."""

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.types import AppDatetime
from app.services.test_run_service import REASON_MAX_LENGTH, TESTER_CODE, Scenario


class TestRunStart(BaseModel):
    # A code such as T01, never a name: no personal data of the tester is kept
    tester_code: str = Field(pattern=f"^{TESTER_CODE.pattern}$")
    scenario: Scenario
    auto_nurses: bool = False


class TestRunStarted(BaseModel):
    test_run_id: int
    scenario: Scenario
    started_at: AppDatetime
    case_id: int | None


class TestRunAbort(BaseModel):
    reason: str | None = Field(default=None, max_length=REASON_MAX_LENGTH)


class TestRunClosed(BaseModel):
    test_run_id: int
    # The payload of TEST_RUN_FINISHED: invalid and reason, or the KPI
    result: dict[str, Any]
