from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Shift
from app.db.models.staffing_case import StaffingCase
from app.domain.enums import ActorName, AuditAction, CaseStatus, EntityType
from app.domain.staffing.gap_calculator import CountGap
from app.services import actor_service, audit_service, gap_service
from app.workflow.handlers.base import HandlerResult


class NoGapError(RuntimeError):
    """The shift of the case is covered. Section 5 has no transition for this yet."""


def handle(db: Session, case: StaffingCase) -> HandlerResult:
    """Store the gap of the case's shift, then request candidate optimization."""
    shift = db.scalars(select(Shift).where(Shift.id == case.shift_id)).one()
    # Same function as event intake (seam 10), so both judge the same roster,
    # requirement and policy
    assessment = gap_service.assess_shift(db, shift)
    result = assessment.result
    if not result.has_gap:
        raise NoGapError(f"Shift {shift.id} of case {case.id} has no staffing gap")

    gap = gap_service.record_gap(db, case, assessment)
    audit_service.log(
        db,
        case_id=case.id,
        actor_id=actor_service.component_id(db, ActorName.STAFFING_GAP_ASSESSMENT_AGENT),
        action=AuditAction.GAP_ASSESSED,
        entity_type=EntityType.STAFFING_GAP,
        entity_id=gap.id,
        payload={
            "gap_id": gap.id,
            "headcount_gap": gap.headcount_gap,
            "role_gaps": _counts("role_id", result.role_gaps),
            "skill_gaps": _counts("skill_id", result.skill_gaps),
        },
    )
    return HandlerResult(next_status=CaseStatus.OPTIMIZING)


def _counts(id_key: str, gaps: Mapping[int, CountGap]) -> list[dict[str, Any]]:
    """A list ordered by ID: JSON would turn integer mapping keys into text."""
    return [
        {
            id_key: item_id,
            "required_count": count.required_count,
            "current_count": count.current_count,
            "gap_count": count.gap_count,
        }
        for item_id, count in sorted(gaps.items())
    ]
