"""Routes for the job service only (docs/workflow.md, section 3.8). Not for a browser."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.api.dependencies import DbSession
from app.core.config import settings
from app.schemas.job import DueWorkResult
from app.services import job_service

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
    x_internal_secret: Annotated[str | None, Header(alias=SECRET_HEADER)] = None,
) -> DueWorkResult:
    """Expire offers, recover missed notifications and close due windows.

    The job service calls this every 30 seconds. A shift whose close fails is
    skipped and tried again on the next call.
    """
    _require_job_secret(x_internal_secret)
    return DueWorkResult.of(job_service.run_due_work(db))
