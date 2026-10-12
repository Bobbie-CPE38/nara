"""Select Wave members from the immutable plan (workflow.md 6.6).

The handler owns OFFER_SENT and MANUAL_HANDOFF. No commit or case-status write.
"""

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    CandidateItem,
    CandidateItemTarget,
    CandidateOutreach,
    CandidatePlan,
    Shift,
)
from app.domain.enums import AuditAction
from app.domain.staffing.wave_targets import fill_targets
from app.domain.workflow.case_status import GapFiller
from app.services import availability_service, case_facts_service, gap_service, hard_rule_service
from app.services.optimization_service import record_item_targets


@dataclass(frozen=True)
class WaveSelection:
    items: tuple[CandidateItem, ...]
    skipped: tuple[dict[str, int | str], ...]
    wave: int


def plan_items(db: Session, case_id: int) -> list[CandidateItem]:
    db.flush()
    plan_id = db.scalar(
        select(CandidatePlan.id)
        .where(CandidatePlan.case_id == case_id)
        .order_by(CandidatePlan.id.desc())
        .limit(1)
    )
    if plan_id is None:
        raise LookupError(f"No candidate plan for case {case_id}")
    return list(
        db.scalars(
            select(CandidateItem)
            .where(CandidateItem.plan_id == plan_id)
            .order_by(CandidateItem.rank, CandidateItem.id)
        )
    )


def select_wave(db: Session, *, case_id: int, shift: Shift) -> WaveSelection:
    items = plan_items(db, case_id)
    hard_rule_service.lock_staff(db, [item.staff_id for item in items])
    history = list(
        db.scalars(
            select(CandidateOutreach)
            .where(CandidateOutreach.case_id == case_id)
            .order_by(CandidateOutreach.id)
        )
    )
    contacted_item_ids = {row.candidate_item_id for row in history}
    contacted_staff_ids = set(
        db.scalars(select(CandidateItem.staff_id).where(CandidateItem.id.in_(contacted_item_ids)))
    )
    remaining = [item for item in items if item.staff_id not in contacted_staff_ids]
    checks = hard_rule_service.check_items(db, shift=shift, items=remaining)
    limited = availability_service.staff_at_offer_limit(db, [item.staff_id for item in remaining])
    skipped: list[dict[str, int | str]] = []
    eligible: list[CandidateItem] = []
    for item in remaining:
        failures = checks[item.id].result.failed_rules
        reason = (
            failures[0].value
            if failures
            else ("OFFER_LIMIT_REACHED" if item.staff_id in limited else None)
        )
        if reason is None:
            eligible.append(item)
        else:
            skipped.append({"staff_id": item.staff_id, "reason": reason})

    gap = gap_service.get_case_gap(db, case_id)
    fillers = case_facts_service.get_case_fillers(db, case_id, include_reserves=True)
    roles = Counter(person.role_id for person in fillers)
    skills = Counter(skill for person in fillers for skill in person.skill_ids)
    head = max(gap.headcount_gap - len(fillers), 0)
    role_gaps = {key: max(value - roles[key], 0) for key, value in gap.role_gaps.items()}
    skill_gaps = {key: max(value - skills[key], 0) for key, value in gap.skill_gaps.items()}

    def person(item: CandidateItem) -> GapFiller:
        context = checks[item.id].context
        return GapFiller(item.staff_id, context.role_id, context.skill_ids)

    target_item_ids = set(
        db.scalars(
            select(CandidateItemTarget.candidate_item_id).where(
                CandidateItemTarget.candidate_item_id.in_([item.id for item in items])
            )
        )
    )
    # Existing target rows identify the Solver's group only before the first send.
    kept = [item for item in eligible if item.id in target_item_ids] if not history else []
    candidates = [item for item in eligible if item not in kept]
    credits = fill_targets(
        headcount_gap=head,
        role_gaps=role_gaps,
        skill_gaps=skill_gaps,
        candidates=[person(item) for item in candidates],
        already_selected=[person(item) for item in kept],
    )
    for item in candidates:
        if item.staff_id in credits:
            # Uncontacted Solver members may be selected for different targets in
            # a later wave. Replace their provisional credits before first send;
            # targets of anyone already contacted remain immutable.
            if item.id in target_item_ids:
                db.execute(
                    delete(CandidateItemTarget).where(
                        CandidateItemTarget.candidate_item_id == item.id
                    )
                )
            record_item_targets(db, item, credits[item.staff_id])
    chosen = [item for item in eligible if item in kept or item.staff_id in credits]
    # Every new wave writes its number on all OFFER_SENT audit rows in the
    # same transaction as the offers. Legacy history without this field is
    # wave 1, so the next send is wave 2. Frozen clocks cannot identify waves.
    previous = list(
        db.scalars(
            select(AuditLog.payload).where(
                AuditLog.case_id == case_id, AuditLog.action == AuditAction.OFFER_SENT
            )
        )
    )
    wave = (
        max((int(payload.get("wave", 1)) for payload in previous), default=1 if history else 0) + 1
    )
    return WaveSelection(tuple(chosen), tuple(skipped), wave)
