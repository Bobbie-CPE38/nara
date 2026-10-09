"""
Read models of a case for the API: its status with gap and candidates, and its
timeline. Read-only.

"Latest" always means the highest id, never a time column: the demo clock is
frozen after a reset, so rows of one case can share the same time
(docs/workflow.md, section 6.4).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Actor,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    Role,
    Skill,
    Staff,
    StaffingCase,
    StaffingGap,
    StaffingGapRole,
    StaffingGapSkill,
)
from app.schemas.case import AuditEntry, CandidateView, CaseDetail, GapCount, GapView
from app.workflow.orchestrator import CaseNotFoundError


def get_case_detail(db: Session, case_id: int) -> CaseDetail:
    case = _get_case(db, case_id)
    return CaseDetail(
        id=case.id,
        status=case.status,
        event_id=case.event_id,
        shift_id=case.shift_id,
        required_replacement_time=case.required_replacement_time,
        created_at=case.created_at,
        updated_at=case.updated_at,
        gap=_latest_gap(db, case.id),
        candidates=_latest_candidates(db, case.id),
    )


def get_case_timeline(db: Session, case_id: int) -> list[AuditEntry]:
    """Audit rows of the case, oldest first (section 6.4, seam 9)."""
    case = _get_case(db, case_id)
    rows = db.execute(
        select(AuditLog, Actor.name, Actor.actor_type)
        .join(Actor, Actor.id == AuditLog.actor_id)
        .where(AuditLog.case_id == case.id)
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


def _latest_candidates(db: Session, case_id: int) -> list[CandidateView]:
    # Section 6.4, seam 1. A case without a plan is normal here: it has not
    # reached the solver yet, so this returns an empty list instead of raising
    plan_id = db.scalar(
        select(CandidatePlan.id)
        .where(CandidatePlan.case_id == case_id)
        .order_by(CandidatePlan.id.desc())
        .limit(1)
    )
    if plan_id is None:
        return []
    items = db.execute(
        select(CandidateItem, Staff.first_name, Staff.last_name)
        .join(Staff, Staff.id == CandidateItem.staff_id)
        .where(CandidateItem.plan_id == plan_id)
        .order_by(CandidateItem.rank, CandidateItem.id)
    ).all()

    # The newest outreach of each item: ascending id, so a later row overwrites
    outreach_status = {
        item_id: status
        for item_id, status in db.execute(
            select(CandidateOutreach.candidate_item_id, CandidateOutreach.status)
            .where(CandidateOutreach.case_id == case_id)
            .order_by(CandidateOutreach.id)
        )
    }
    return [
        CandidateView(
            candidate_item_id=item.id,
            rank=item.rank,
            staff_id=item.staff_id,
            first_name=first_name,
            last_name=last_name,
            source=item.source,
            outreach_status=outreach_status.get(item.id),
        )
        for item, first_name, last_name in items
    ]
