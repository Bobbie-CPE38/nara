"""Routes for the job service and trusted administrator CLI; not for a browser."""

import secrets
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Path, Response, status

from app.api.dependencies import DbSession
from app.core.config import settings
from app.core.constants import MAX_BIGINT
from app.schemas.job import DueWorkResult
from app.schemas.line_account import IssuedLineCode, UnlinkedLineAccount
from app.services import explanation_service, job_service, line_account_service

router = APIRouter(prefix="/internal", tags=["internal"])

SECRET_HEADER = "X-Internal-Secret"


def _require_job_secret(sent: str | None) -> None:
    expected = settings.internal_job_secret
    if expected is None:
        # Closed, not open, when nobody configured a secret
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "INTERNAL_JOB_SECRET is not configured"
        )
    if sent is None or not secrets.compare_digest(sent.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Missing or wrong {SECRET_HEADER}")


@router.post("/merge-windows/close-due")
def close_due_merge_windows(
    db: DbSession,
    background_tasks: BackgroundTasks,
    x_internal_secret: Annotated[str | None, Header(alias=SECRET_HEADER)] = None,
) -> DueWorkResult:
    """Expire offers, recover missed notifications and close due windows.

    The job service calls this every 30 seconds. A shift whose close fails is
    skipped and tried again on the next call.
    """
    _require_job_secret(x_internal_secret)
    result = DueWorkResult.of(job_service.run_due_work(db))
    # LLM sentences run after the response with their own Session, so the tick never waits
    background_tasks.add_task(explanation_service.run_pending_in_new_session)
    return result


@router.post("/line-accounts/{staff_id}/issue-code", response_model=IssuedLineCode)
def issue_line_code(
    staff_id: Annotated[int, Path(ge=1, le=MAX_BIGINT)],
    db: DbSession,
    response: Response,
    x_internal_secret: Annotated[str | None, Header(alias=SECRET_HEADER)] = None,
) -> IssuedLineCode:
    """Administrator CLI uses the Backend's Clock, including a frozen demo Clock."""
    _require_job_secret(x_internal_secret)
    try:
        issued = line_account_service.issue_code(db, staff_id)
        db.commit()
    except line_account_service.LineAccountError as error:
        db.rollback()
        code = 404 if isinstance(error, line_account_service.LinkStaffUnavailableError) else 409
        raise HTTPException(code, str(error)) from None
    response.headers["Cache-Control"] = "no-store"
    return IssuedLineCode(code=issued.code.get_secret_value(), expires_at=issued.expires_at)


@router.post("/line-accounts/{staff_id}/unlink", response_model=UnlinkedLineAccount)
def unlink_line_account(
    staff_id: Annotated[int, Path(ge=1, le=MAX_BIGINT)],
    db: DbSession,
    x_internal_secret: Annotated[str | None, Header(alias=SECRET_HEADER)] = None,
) -> UnlinkedLineAccount:
    _require_job_secret(x_internal_secret)
    try:
        count = line_account_service.unlink(db, staff_id)
        db.commit()
    except line_account_service.LineAccountError as error:
        db.rollback()
        raise HTTPException(404, str(error)) from None
    return UnlinkedLineAccount(unlinked_contacts=count)
