"""Case status and timeline (docs/workflow.md, section 9.3), read without X-Demo-User,
and the manual exits of MANUAL_HANDOFF (sections 6.12 and 9.4), which need a head nurse."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BeforeValidator

from app.api.dependencies import DbSession, DemoUser
from app.domain.enums import CaseStatus
from app.domain.errors import CaseNotFoundError
from app.schemas.case import AuditEntry, CaseDetail
from app.schemas.handoff import (
    CloseCaseRequest,
    CloseCaseResult,
    HandoffCandidate,
    HandoffCase,
    ManualAssignmentRequest,
    ManualAssignmentResult,
)
from app.schemas.types import MAX_BIGINT
from app.services import case_service, handoff_service, handover_service

router = APIRouter(prefix="/cases", tags=["cases"])

# Out of the bigint range is a 422 here. Without the bounds a huge number
# reaches PostgreSQL and comes back as a 500
CaseId = Annotated[int, Path(ge=1, le=MAX_BIGINT)]


def _split_statuses(values: object) -> object:
    """Accept `?status=MANUAL_HANDOFF,FAILED` as well as a repeated `status`."""
    if not isinstance(values, list):
        return values
    names = [name.strip() for value in values for name in str(value).split(",")]
    return list(dict.fromkeys(names))


StatusFilter = Annotated[
    list[CaseStatus], BeforeValidator(_split_statuses), Query(alias="status", min_length=1)
]


@router.get("")
def list_cases(db: DbSession, user: DemoUser, statuses: StatusFilter) -> list[HandoffCase]:
    """Cases of the caller's ward in the given statuses (`status` is required).

    For the head nurse's handoff list: `?status=MANUAL_HANDOFF,FAILED`.
    """
    try:
        return handoff_service.list_cases(
            db,
            role_id=user.staff.role_id,
            home_ward_id=user.staff.home_ward_id,
            statuses=statuses,
        )
    except handoff_service.HandoffForbiddenError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error


@router.get("/{case_id}")
def get_case(case_id: CaseId, db: DbSession) -> CaseDetail:
    """Status of the case with its latest gap and candidates. 404 for an unknown case."""
    return case_service.get_case_detail(db, case_id)


@router.get("/{case_id}/audit")
def get_case_audit(case_id: CaseId, db: DbSession) -> list[AuditEntry]:
    """Timeline of the case as a plain list, oldest first. 404 for an unknown case."""
    return case_service.get_case_timeline(db, case_id)


@router.get("/{case_id}/handoff/candidates")
def handoff_candidates(case_id: CaseId, db: DbSession, user: DemoUser) -> list[HandoffCandidate]:
    """Active staff of the shift's ward with the Hard Rules that block each one."""
    try:
        return handoff_service.list_candidates(
            db,
            case_id=case_id,
            role_id=user.staff.role_id,
            home_ward_id=user.staff.home_ward_id,
        )
    except CaseNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except handoff_service.HandoffForbiddenError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error


@router.post("/{case_id}/handoff/assignments", response_model=ManualAssignmentResult)
def assign_manually(
    case_id: CaseId, body: ManualAssignmentRequest, db: DbSession, user: DemoUser
) -> ManualAssignmentResult:
    """Put one person on the shift of a MANUAL_HANDOFF case (T8 once the gap is closed)."""
    try:
        outcome = handoff_service.assign(
            db,
            case_id=case_id,
            staff_id=body.staff_id,
            assigned_by=user.staff.id,
            role_id=user.staff.role_id,
            home_ward_id=user.staff.home_ward_id,
            actor_id=user.actor_id,
            reason=body.reason,
            confirm_conflicts=body.confirm_conflicts,
        )
    except CaseNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except handoff_service.HandoffForbiddenError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except handoff_service.HardRulesFailedError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "HARD_RULES_FAILED",
                "message": str(error),
                "failed_rules": error.failed_rules,
            },
        ) from error
    except handoff_service.ConflictingOffersError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "CONFLICTING_OFFERS",
                "message": str(error),
                "case_ids": error.case_ids,
            },
        ) from error
    except handover_service.HandoverProvenanceError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "HANDOVER_SOURCE_UNAVAILABLE", "message": str(error)},
        ) from error
    except (
        handoff_service.HandoffCaseStateError,
        handoff_service.HandoffLockRetryError,
    ) as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    except (
        handoff_service.StaffNotSelectableError,
        handoff_service.InvalidHandoffReasonError,
    ) as error:
        raise HTTPException(422, detail=str(error)) from error
    return ManualAssignmentResult(**outcome._asdict())


@router.post("/{case_id}/handoff/close", response_model=CloseCaseResult)
def close_without_replacement(
    case_id: CaseId, body: CloseCaseRequest, db: DbSession, user: DemoUser
) -> CloseCaseResult:
    """Close a MANUAL_HANDOFF case as UNRESOLVED with a reason (T9)."""
    try:
        case = handoff_service.close(
            db,
            case_id=case_id,
            role_id=user.staff.role_id,
            home_ward_id=user.staff.home_ward_id,
            actor_id=user.actor_id,
            reason=body.reason,
        )
    except CaseNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except handoff_service.HandoffForbiddenError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except handoff_service.HandoffCaseStateError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from error
    except handoff_service.InvalidHandoffReasonError as error:
        raise HTTPException(422, detail=str(error)) from error
    return CloseCaseResult(case_id=case.id, case_status=case.status)
