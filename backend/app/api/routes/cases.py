"""Case status and timeline (docs/workflow.md, section 9.3), the request for the ranking
explanation (section 9.8), and the manual exits of MANUAL_HANDOFF (sections 6.12 and 9.4),
which need a head nurse.

Demo mode reads a case without X-Demo-User. Session mode needs a signed-in user who may
see the case (6.33.4, round 6 PR AU2): 401, then 404 for an unknown case, then 403.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BeforeValidator

from app.api.dependencies import (
    CurrentUser,
    DbSession,
    DemoUser,
    Reader,
    access_viewer,
    forbidden,
    session_mode,
)
from app.domain.enums import CaseStatus, ExplanationBlock
from app.domain.errors import CaseNotFoundError
from app.schemas.case import AuditEntry, CaseDetail, RankExplanationView
from app.schemas.case_summary import CaseSummaryView
from app.schemas.handoff import (
    CasePage,
    CloseCaseRequest,
    CloseCaseResult,
    HandoffCandidate,
    HandoffCase,
    ManualAssignmentRequest,
    ManualAssignmentResult,
)
from app.schemas.types import MAX_BIGINT
from app.services import (
    access_service,
    case_service,
    case_summary_service,
    explanation_service,
    handoff_service,
    handover_service,
)

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


def _check_case(db: DbSession, reader: CurrentUser | None, case_id: int) -> None:
    """404 in session mode for a case the user may not see, the same as an unknown case: an
    ID cannot be probed. Demo mode (no reader) checks nothing."""
    if reader is not None and not access_service.sees_case(db, access_viewer(db, reader), case_id):
        raise CaseNotFoundError(f"No case {case_id}")


def _check_manager(db: DbSession, reader: CurrentUser | None) -> None:
    """Asking the LLM queues model work and uses the shared daily quota, so it is for a head
    nurse or a supervisor, not for a nurse who may only read the case (6.33.4)."""
    if reader is not None and access_viewer(db, reader).role == "staff":
        raise forbidden()


@router.get("")
def list_cases(db: DbSession, user: DemoUser, statuses: StatusFilter) -> list[HandoffCase]:
    """Cases of the caller's ward in the given statuses (`status` is required).

    For the head nurse's handoff list: `?status=MANUAL_HANDOFF,FAILED`. In session mode a
    staff member gets only the cases they are part of (6.33.4), filtered in the query.
    """
    viewer = access_viewer(db, user) if session_mode() else None
    try:
        return handoff_service.list_cases(
            db,
            role_id=user.staff.role_id,
            home_ward_id=user.staff.home_ward_id,
            statuses=statuses,
            condition=access_service.case_condition(viewer)
            if viewer is not None and viewer.role == "staff"
            else None,
        )
    except handoff_service.HandoffForbiddenError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error


OptionalStatusFilter = Annotated[
    list[CaseStatus] | None, BeforeValidator(_split_statuses), Query(alias="status")
]
CASE_PAGE_SIZE_MAX = 100


@router.get("/search")
def search_cases(
    db: DbSession,
    user: DemoUser,
    statuses: OptionalStatusFilter = None,
    ward_id: Annotated[int | None, Query(ge=1, le=MAX_BIGINT)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=CASE_PAGE_SIZE_MAX)] = 20,
    sort: Annotated[Literal["newest", "oldest"], Query()] = "newest",
) -> CasePage:
    """One page of the cases the caller may read, for the case list and the handoff page
    (round 6 PR EV6, 6.36.6). The same rows as GET /cases, any status unless `status`
    names some; `q` is a case or shift ID, or part of a ward name."""
    viewer = access_viewer(db, user) if session_mode() else None
    try:
        return handoff_service.search_cases(
            db,
            role_id=user.staff.role_id,
            home_ward_id=user.staff.home_ward_id,
            condition=access_service.case_condition(viewer)
            if viewer is not None and viewer.role == "staff"
            else None,
            statuses=statuses,
            ward_id=ward_id,
            query=q,
            page=page,
            page_size=page_size,
            oldest_first=sort == "oldest",
        )
    except handoff_service.HandoffForbiddenError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(error)) from error


@router.get("/{case_id}")
def get_case(case_id: CaseId, db: DbSession, reader: Reader) -> CaseDetail:
    """Status of the case with its latest gap and candidates. 404 for an unknown case."""
    _check_case(db, reader, case_id)
    return case_service.get_case_detail(db, case_id)


# Round 6 PR E1 (docs/workflow.md 9.8): how a refused explanation request answers
_EXPLANATION_REFUSALS: dict[ExplanationBlock, tuple[int, str]] = {
    ExplanationBlock.NOT_CONFIGURED: (status.HTTP_409_CONFLICT, "LLM_UNAVAILABLE"),
    ExplanationBlock.INVALID_INPUT: (status.HTTP_409_CONFLICT, "LLM_UNAVAILABLE"),
    ExplanationBlock.ATTEMPTS_EXHAUSTED: (status.HTTP_409_CONFLICT, "LLM_ATTEMPTS_EXHAUSTED"),
    ExplanationBlock.QUOTA_EXHAUSTED: (
        status.HTTP_429_TOO_MANY_REQUESTS,
        "LLM_QUOTA_EXHAUSTED",
    ),
}
_EXPLANATION_MESSAGES: dict[ExplanationBlock, str] = {
    ExplanationBlock.NOT_CONFIGURED: "The LLM is switched off or not configured",
    ExplanationBlock.INVALID_INPUT: "This plan cannot be explained",
    ExplanationBlock.ATTEMPTS_EXHAUSTED: "This plan's explanation has used all its attempts",
    ExplanationBlock.QUOTA_EXHAUSTED: "Today's AI explanation quota is used up",
}


@router.post("/{case_id}/explanation")
def request_explanation(case_id: CaseId, db: DbSession, reader: Reader) -> RankExplanationView:
    """Ask for the LLM explanation of the latest plan. Never calls the LLM itself: the Job
    makes the sentence later. An answered request returns the row unchanged; a refused
    one changes nothing and uses no quota (section 9.8). In session mode: a head nurse or a
    supervisor who may read the case (403 for a nurse, 404 for a case that is not theirs)."""
    _check_manager(db, reader)
    try:
        _check_case(db, reader, case_id)
        return explanation_service.request(db, case_id)
    except CaseNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"code": "CASE_NOT_FOUND", "message": str(error)}
        ) from error
    except explanation_service.ExplanationRequestError as error:
        code, name = _EXPLANATION_REFUSALS[error.block]
        raise HTTPException(
            code, detail={"code": name, "message": _EXPLANATION_MESSAGES[error.block]}
        ) from error


@router.post("/{case_id}/summary")
def request_summary(case_id: CaseId, db: DbSession, reader: Reader) -> CaseSummaryView:
    """Queue the current anonymous snapshot. No model call in this request. In session mode: a
    head nurse or a supervisor who may read the case, as for the explanation."""
    _check_manager(db, reader)
    try:
        _check_case(db, reader, case_id)
        return case_summary_service.request(db, case_id)
    except CaseNotFoundError as error:
        raise HTTPException(
            404, detail={"code": "CASE_NOT_FOUND", "message": str(error)}
        ) from error
    except explanation_service.ExplanationRequestError as error:
        status_code, code = _EXPLANATION_REFUSALS[error.block]
        raise HTTPException(
            status_code, detail={"code": code, "message": "Cannot request a case summary now"}
        ) from error


@router.get("/{case_id}/audit")
def get_case_audit(case_id: CaseId, db: DbSession, reader: Reader) -> list[AuditEntry]:
    """Timeline of the case as a plain list, oldest first. 404 for an unknown case."""
    _check_case(db, reader, case_id)
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
