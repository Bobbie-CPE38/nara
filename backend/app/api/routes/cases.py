"""Case status and timeline (docs/workflow.md, section 9.3). Read-only, no X-Demo-User needed."""

from typing import Annotated

from fastapi import APIRouter, Path

from app.api.dependencies import DbSession
from app.schemas.case import AuditEntry, CaseDetail
from app.schemas.types import MAX_BIGINT
from app.services import case_service

router = APIRouter(prefix="/cases", tags=["cases"])

# Out of the bigint range is a 422 here. Without the bounds a huge number
# reaches PostgreSQL and comes back as a 500
CaseId = Annotated[int, Path(ge=1, le=MAX_BIGINT)]


@router.get("/{case_id}")
def get_case(case_id: CaseId, db: DbSession) -> CaseDetail:
    """Status of the case with its latest gap and candidates. 404 for an unknown case."""
    return case_service.get_case_detail(db, case_id)


@router.get("/{case_id}/audit")
def get_case_audit(case_id: CaseId, db: DbSession) -> list[AuditEntry]:
    """Timeline of the case as a plain list, oldest first. 404 for an unknown case."""
    return case_service.get_case_timeline(db, case_id)
