"""
Read models of a case for the API: its status with gap and candidates, and its
timeline. Read-only.

"Latest" always means the highest id, never a time column: the demo clock is
frozen after a reset, so rows of one case can share the same time
(docs/workflow.md, section 6.4).
"""

import logging
from datetime import datetime
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
    Role,
    RosterAssignment,
    SafetyValidation,
    Shift,
    Skill,
    Staff,
    StaffingCase,
    StaffingEvent,
    StaffingGap,
    StaffingGapInterval,
    StaffingGapRole,
    StaffingGapRoleInterval,
    StaffingGapSkill,
    StaffingGapSkillInterval,
    Ward,
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
from app.domain.enums import OutreachStatus
from app.domain.errors import CaseNotFoundError
from app.schemas.case import (
    AuditEntry,
    CandidateScore,
    CandidateStage,
    CandidateView,
    CaseDetail,
    GapCount,
    GapIntervalView,
    GapView,
    HeadcountCount,
    RankExplanationView,
    ScoreTerm,
    SourceAssignmentView,
)
from app.services import (
    case_facts_service,
    case_overview_service,
    case_summary_service,
    explanation_service,
    handover_service,
)

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
        partial_plan=_partial_plan(db, case.id),
        handovers=handover_service.list_handovers(db, case_id=case.id),
        summary=case_summary_service.view(db, case),
        overview=case_overview_service.build(db, case.id),
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
        evaluated_from=gap.evaluated_from,
        intervals=_gap_intervals(db, gap.id),
    )


def _gap_intervals(db: Session, gap_id: int) -> list[GapIntervalView]:
    """Every time slice of a gap in time order, with role and skill counts by ID."""
    roles: dict[datetime, list[GapCount]] = {}
    for role_row, name in db.execute(
        select(StaffingGapRoleInterval, Role.name)
        .join(Role, Role.id == StaffingGapRoleInterval.role_id)
        .where(StaffingGapRoleInterval.gap_id == gap_id)
        .order_by(StaffingGapRoleInterval.role_id)
    ):
        roles.setdefault(role_row.start_at, []).append(
            GapCount(
                id=role_row.role_id,
                name=name,
                required_count=role_row.required_count,
                current_count=role_row.current_count,
                gap_count=role_row.gap_count,
            )
        )
    skills: dict[datetime, list[GapCount]] = {}
    for skill_row, name in db.execute(
        select(StaffingGapSkillInterval, Skill.name)
        .join(Skill, Skill.id == StaffingGapSkillInterval.skill_id)
        .where(StaffingGapSkillInterval.gap_id == gap_id)
        .order_by(StaffingGapSkillInterval.skill_id)
    ):
        skills.setdefault(skill_row.start_at, []).append(
            GapCount(
                id=skill_row.skill_id,
                name=name,
                required_count=skill_row.required_count,
                current_count=skill_row.current_count,
                gap_count=skill_row.gap_count,
            )
        )
    return [
        GapIntervalView(
            start_at=row.start_at,
            end_at=row.end_at,
            headcount=HeadcountCount(
                required_count=row.required_count,
                current_count=row.current_count,
                gap_count=row.gap_count,
            ),
            roles=roles.get(row.start_at, []),
            skills=skills.get(row.start_at, []),
        )
        for row in db.scalars(
            select(StaffingGapInterval)
            .where(StaffingGapInterval.gap_id == gap_id)
            .order_by(StaffingGapInterval.start_at)
        )
    ]


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


def _partial_plan(db: Session, case_id: int) -> bool:
    """True when the latest plan was a partial plan; False without a plan."""
    plan = _latest_plan(db, case_id)
    return plan is not None and bool(plan.input_snapshot.get("partial_plan", False))


def _latest_explanation(db: Session, case_id: int) -> RankExplanationView | None:
    """The explanation of the latest plan with whether it can be asked for now; null if
    there is no plan or it has no candidates (round 6 PR E1).

    Only a READY row exposes its text, provider and model. The failure reason is never
    returned.
    """
    return explanation_service.view(db, _latest_plan(db, case_id))


def _latest_candidates(db: Session, case_id: int) -> list[CandidateView]:
    plan = _latest_plan(db, case_id)
    if plan is None:
        return []
    plan_id = plan.id
    items = db.execute(
        select(CandidateItem, Staff.first_name, Staff.last_name, Ward.id, Ward.name)
        .join(Staff, Staff.id == CandidateItem.staff_id)
        .join(Ward, Ward.id == Staff.home_ward_id)
        .where(CandidateItem.plan_id == plan_id)
        .order_by(CandidateItem.rank, CandidateItem.id)
    ).all()
    scores = _scores(plan, [item.staff_id for item, *_ in items])

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
    sources = _source_assignments(db, [item.source_assignment_id for item, *_ in items])
    return [
        CandidateView(
            candidate_item_id=item.id,
            rank=item.rank,
            staff_id=item.staff_id,
            first_name=first_name,
            last_name=last_name,
            source=item.source,
            home_ward_id=home_ward_id,
            home_ward_name=home_ward_name,
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
            cover_start_at=item.cover_start_at,
            cover_end_at=item.cover_end_at,
            source_assignment=(
                sources[item.source_assignment_id]
                if item.source_assignment_id is not None
                else None
            ),
        )
        for item, first_name, last_name, home_ward_id, home_ward_name in items
    ]


def _source_assignments(
    db: Session, assignment_ids: list[int | None]
) -> dict[int, SourceAssignmentView]:
    """The source roster rows of a plan's items, by assignment ID, in one query."""
    ids = {assignment_id for assignment_id in assignment_ids if assignment_id is not None}
    if not ids:
        return {}
    return {
        assignment_id: SourceAssignmentView(
            assignment_id=assignment_id, shift_id=shift_id, ward_id=ward_id, ward_name=ward_name
        )
        for assignment_id, shift_id, ward_id, ward_name in db.execute(
            select(RosterAssignment.id, Shift.id, Ward.id, Ward.name)
            .join(Shift, Shift.id == RosterAssignment.shift_id)
            .join(Ward, Ward.id == Shift.ward_id)
            .where(RosterAssignment.id.in_(ids))
        )
    }


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
