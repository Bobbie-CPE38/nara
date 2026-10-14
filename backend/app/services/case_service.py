"""
Read models of a case for the API: its status with gap and candidates, and its
timeline. Read-only.

"Latest" always means the highest id, never a time column: the demo clock is
frozen after a reset, so rows of one case can share the same time
(docs/workflow.md, section 6.4).
"""

import logging
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Actor,
    ApprovalRequest,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    RankExplanation,
    Role,
    SafetyValidation,
    Skill,
    Staff,
    StaffingCase,
    StaffingEvent,
    StaffingGap,
    StaffingGapRole,
    StaffingGapSkill,
)
from app.domain.constraints.score_breakdown import (
    CandidateScore as ScoreBreakdown,
)
from app.domain.constraints.score_breakdown import (
    ScoreMismatchError,
    display_number,
    score_from_snapshot,
    weights_from_snapshot,
)
from app.domain.enums import ExplanationStatus, OutreachStatus
from app.domain.errors import CaseNotFoundError
from app.schemas.case import (
    AuditEntry,
    CandidateScore,
    CandidateStage,
    CandidateView,
    CaseDetail,
    GapCount,
    GapView,
    RankExplanationView,
    ScoreTerm,
)
from app.services import case_facts_service

logger = logging.getLogger(__name__)

_OFFER_STAGES: dict[OutreachStatus, CandidateStage] = {
    OutreachStatus.PENDING: "OFFER_PENDING",
    OutreachStatus.SENT: "OFFER_SENT",
    OutreachStatus.REJECTED: "OFFER_REJECTED",
    OutreachStatus.TIMEOUT: "OFFER_TIMEOUT",
    OutreachStatus.FAILED: "OFFER_FAILED",
    OutreachStatus.CANCELLED: "OFFER_CANCELLED",
}


def get_case_detail(db: Session, case_id: int) -> CaseDetail:
    case = _get_case(db, case_id)
    return CaseDetail(
        id=case.id,
        status=case.status,
        event_ids=_event_ids(db, case.id),
        shift_id=case.shift_id,
        required_replacement_time=case.required_replacement_time,
        created_at=case.created_at,
        updated_at=case.updated_at,
        gap=_latest_gap(db, case.id),
        assigned_count=len(case_facts_service.assigned_staff_ids(db, case.id)),
        candidates=_latest_candidates(db, case.id),
        explanation=_latest_explanation(db, case.id),
    )


def get_case_timeline(db: Session, case_id: int) -> list[AuditEntry]:
    """Audit rows of the case and of its events, oldest first (section 6.4, seam 9).

    A row about an event has event_id and no case_id (section 3.7). It was
    written before the case existed, so it comes before CASE_OPENED.
    """
    case = _get_case(db, case_id)
    rows = db.execute(
        select(AuditLog, Actor.name, Actor.actor_type)
        .join(Actor, Actor.id == AuditLog.actor_id)
        .where(
            or_(
                AuditLog.case_id == case.id,
                AuditLog.event_id.in_(
                    select(StaffingEvent.id).where(StaffingEvent.case_id == case.id)
                ),
            )
        )
        # By id: every row of a demo run carries the same frozen created_at
        .order_by(AuditLog.id)
    )
    return [
        AuditEntry(
            id=entry.id,
            action=entry.action,
            actor_id=entry.actor_id,
            actor_name=actor_name,
            actor_type=actor_type,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            payload=entry.payload,
            created_at=entry.created_at,
        )
        for entry, actor_name, actor_type in rows
    ]


def _get_case(db: Session, case_id: int) -> StaffingCase:
    case = db.get(StaffingCase, case_id)
    if case is None:
        raise CaseNotFoundError(f"No case {case_id}")
    return case


def _event_ids(db: Session, case_id: int) -> list[int]:
    return list(
        db.scalars(
            select(StaffingEvent.id)
            .where(StaffingEvent.case_id == case_id)
            .order_by(StaffingEvent.id)
        )
    )


def _latest_gap(db: Session, case_id: int) -> GapView | None:
    gap = db.scalar(
        select(StaffingGap)
        .where(StaffingGap.case_id == case_id)
        .order_by(StaffingGap.id.desc())
        .limit(1)
    )
    if gap is None:
        return None
    roles = db.execute(
        select(StaffingGapRole, Role.name)
        .join(Role, Role.id == StaffingGapRole.role_id)
        .where(StaffingGapRole.gap_id == gap.id)
        .order_by(StaffingGapRole.role_id)
    )
    skills = db.execute(
        select(StaffingGapSkill, Skill.name)
        .join(Skill, Skill.id == StaffingGapSkill.skill_id)
        .where(StaffingGapSkill.gap_id == gap.id)
        .order_by(StaffingGapSkill.skill_id)
    )
    return GapView(
        id=gap.id,
        effective_minimum=gap.effective_minimum,
        headcount_gap=gap.headcount_gap,
        computed_at=gap.computed_at,
        roles=[
            GapCount(
                id=row.role_id,
                name=name,
                required_count=row.required_count,
                current_count=row.current_count,
                gap_count=row.gap_count,
            )
            for row, name in roles
        ],
        skills=[
            GapCount(
                id=row.skill_id,
                name=name,
                required_count=row.required_count,
                current_count=row.current_count,
                gap_count=row.gap_count,
            )
            for row, name in skills
        ],
    )


def _latest_plan(db: Session, case_id: int) -> CandidatePlan | None:
    # The latest plan as in section 6.4, seam 1. Unlike seam 1, no plan is not
    # an error here: this is a read route, and a case that has not reached the
    # solver yet simply has no candidates to show (section 9.3)
    return db.scalar(
        select(CandidatePlan)
        .where(CandidatePlan.case_id == case_id)
        .order_by(CandidatePlan.id.desc())
        .limit(1)
    )


def _latest_explanation(db: Session, case_id: int) -> RankExplanationView | None:
    """The newest explanation row of the latest plan; null if there is no plan or row.

    FAILED and SKIPPED both read as UNAVAILABLE, and only a READY row exposes its
    text, provider and model. The failure reason is never returned.
    """
    plan = _latest_plan(db, case_id)
    if plan is None:
        return None
    row = db.scalar(
        select(RankExplanation)
        .where(RankExplanation.plan_id == plan.id)
        .order_by(RankExplanation.id.desc())
        .limit(1)
    )
    if row is None:
        return None
    if row.status == ExplanationStatus.READY:
        return RankExplanationView(
            status="READY", text=row.text, provider=row.provider, model_id=row.model_id
        )
    status = "PENDING" if row.status == ExplanationStatus.PENDING else "UNAVAILABLE"
    return RankExplanationView(status=status, text=None, provider=None, model_id=None)


def _latest_candidates(db: Session, case_id: int) -> list[CandidateView]:
    plan = _latest_plan(db, case_id)
    if plan is None:
        return []
    plan_id = plan.id
    items = db.execute(
        select(CandidateItem, Staff.first_name, Staff.last_name)
        .join(Staff, Staff.id == CandidateItem.staff_id)
        .where(CandidateItem.plan_id == plan_id)
        .order_by(CandidateItem.rank, CandidateItem.id)
    ).all()
    scores = _scores(plan, [item.staff_id for item, _, _ in items])

    # The newest outreach of each item: ascending id, so a later row overwrites
    latest_offers = {
        item_id: (offer_id, status)
        for item_id, offer_id, status in db.execute(
            select(
                CandidateOutreach.candidate_item_id, CandidateOutreach.id, CandidateOutreach.status
            )
            .where(CandidateOutreach.case_id == case_id)
            .order_by(CandidateOutreach.id)
        )
    }
    outreach_status = {item_id: status for item_id, (_, status) in latest_offers.items()}
    safety_passed = {
        offer_id: is_passed
        for offer_id, is_passed in db.execute(
            select(SafetyValidation.outreach_id, SafetyValidation.is_passed)
            .where(SafetyValidation.case_id == case_id)
            .order_by(SafetyValidation.id)
        )
    }
    approved = {
        offer_id: (is_approved, is_timed_out)
        for offer_id, is_approved, is_timed_out in db.execute(
            select(
                ApprovalRequest.outreach_id,
                ApprovalRequest.is_approved,
                ApprovalRequest.is_timed_out,
            )
            .where(ApprovalRequest.case_id == case_id, ApprovalRequest.is_pending.is_(False))
            .order_by(ApprovalRequest.id)
        )
    }
    assigned = case_facts_service.assigned_staff_ids(db, case_id)
    pending = case_facts_service.pending_staff_ids(db, case_id)
    return [
        CandidateView(
            candidate_item_id=item.id,
            rank=item.rank,
            staff_id=item.staff_id,
            first_name=first_name,
            last_name=last_name,
            source=item.source,
            outreach_status=outreach_status.get(item.id),
            stage=_stage(
                outreach_status=outreach_status.get(item.id),
                safety_passed=safety_passed.get(latest_offers.get(item.id, (-1, None))[0]),
                approved=approved.get(latest_offers.get(item.id, (-1, None))[0], (None, False))[0],
                is_timed_out=approved.get(latest_offers.get(item.id, (-1, None))[0], (None, False))[
                    1
                ],
                is_assigned=item.staff_id in assigned,
                is_pending=item.staff_id in pending,
            ),
            score=scores[item.staff_id],
        )
        for item, first_name, last_name in items
    ]


def _scores(plan: CandidatePlan, staff_ids: list[int]) -> dict[int, CandidateScore | None]:
    """The score of each candidate, rebuilt from the plan's snapshot alone (section 6.15).

    Never reads the current policy or the float fields. A plan without stored
    weights predates PR E and gets null. A plan with weights whose entry is missing,
    incomplete or does not add up is a bug: that candidate gets null and an error
    is logged, so the rest of the case page still answers. Nothing is rounded to fit.
    """
    snapshot = plan.input_snapshot
    if "weights" not in snapshot:
        return dict.fromkeys(staff_ids)
    try:
        weights = weights_from_snapshot(snapshot["weights"])
    except ScoreMismatchError:
        logger.exception("Plan %s: the stored weights cannot be read", plan.id)
        return dict.fromkeys(staff_ids)
    entries = _snapshot_entries(plan)
    scores: dict[int, CandidateScore | None] = {}
    for staff_id in staff_ids:
        try:
            if staff_id not in entries:
                raise ScoreMismatchError(f"the snapshot has no entry for staff {staff_id}")
            scores[staff_id] = _score_view(score_from_snapshot(weights, entries[staff_id]))
        except ScoreMismatchError:
            logger.exception(
                "Plan %s: the score of staff %s cannot be explained", plan.id, staff_id
            )
            scores[staff_id] = None
    return scores


def _snapshot_entries(plan: CandidatePlan) -> dict[int, Any]:
    """The snapshot entries by staff ID. An entry that cannot be identified is logged
    and left out, so its candidate falls into the missing-entry handling of _scores."""
    rows = plan.input_snapshot.get("candidates")
    if not isinstance(rows, list):
        logger.error("Plan %s: the snapshot has no list of candidates", plan.id)
        return {}
    entries: dict[int, Any] = {}
    for row in rows:
        staff_id = row.get("staff_id") if isinstance(row, dict) else None
        if not isinstance(staff_id, int):
            logger.error("Plan %s: a snapshot entry has no staff ID: %r", plan.id, row)
            continue
        entries[staff_id] = row
    return entries


def _score_view(score: ScoreBreakdown) -> CandidateScore:
    return CandidateScore(
        total=display_number(score.total),
        terms=[
            ScoreTerm(
                name=term.name,
                value=display_number(term.value),
                weight=display_number(term.weight),
                points=display_number(term.points),
            )
            for term in score.terms
        ],
        first_wave=score.first_wave,
    )


def _stage(
    *,
    outreach_status: OutreachStatus | None,
    safety_passed: bool | None,
    approved: bool | None,
    is_assigned: bool,
    is_pending: bool,
    is_timed_out: bool = False,
) -> CandidateStage:
    """The first rule that matches (docs/workflow.md, section 4.1)."""
    if is_assigned:
        return "ASSIGNED"
    if approved is True:
        return "APPROVED"
    if is_timed_out:
        return "APPROVAL_TIMEOUT"
    if approved is False:
        return "APPROVAL_REJECTED"
    if safety_passed is False:
        return "SAFETY_FAILED"
    if outreach_status is None:
        return "NOT_CONTACTED"
    if outreach_status is OutreachStatus.ACCEPTED:
        return "WAITING_APPROVAL" if is_pending else "ACCEPTED"
    return _OFFER_STAGES[outreach_status]
