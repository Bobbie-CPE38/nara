"""
Hard Rules of candidates, checked against the database (round 1 contract, sections 7.2 and 7.3).

Loads what `domain.constraints` needs and runs it. The Solver, wave selection
and Safety all go through this module, so the same rows give the same answer at
all three (Q55).

Role and skill are judged against the targets a candidate is selected to fill:
  * target_skill_ids = the skills of the candidate's SKILL rows in
    CANDIDATE_ITEM_TARGET. No row asks for no skill.
  * target_role_ids = the roles of the candidate's ROLE rows. A candidate with no
    ROLE row (nobody selected them yet, or they fill headcount or a skill only)
    gets the role IDs of the current requirement of the shift instead, so a role
    the shift does not use fails with ROLE_MISMATCH. The set is empty only when
    the requirement lists no role.

Rules:
  * Read-only. Nothing here adds, flushes or commits; lock_staff() only takes
    row locks. The caller flushes what it wants counted.
  * A broken rule is a code in the result, never an exception.
  * The offer cap is not checked here (availability_service.staff_at_offer_limit):
    Safety must not apply it to the candidate's own accepted offer.
  * Roster rows are loaded in a window around the week of the proposed shift
    (see _roster). It assumes no shift is longer than 24 hours.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    CandidateItem,
    CandidateItemTarget,
    HardConstraintPolicy,
    RosterAssignment,
    Shift,
    Staff,
    StaffUnavailability,
)
from app.domain.constraints.context import (
    MAX_REST_WITHIN_RUN,
    CandidateContext,
    HardRulePolicy,
    RosterEntry,
    ShiftSlot,
    UnavailabilityPeriod,
    week_start,
)
from app.domain.constraints.evaluator import HardRuleResult, evaluate
from app.domain.enums import TargetType
from app.services import gap_service, policy_service, requirement_service

_LONGEST_SHIFT = timedelta(hours=24)


@dataclass(frozen=True)
class CandidateCheck:
    """The Hard Rule inputs and outcome of one candidate."""

    context: CandidateContext
    result: HardRuleResult


@dataclass(frozen=True)
class _Targets:
    """Roles and skills of a candidate's target rows. Both empty = no row yet."""

    role_ids: frozenset[int] = frozenset()
    skill_ids: frozenset[int] = frozenset()


_NO_TARGETS = _Targets()


def to_policy(policy: HardConstraintPolicy) -> HardRulePolicy:
    """The values of a HARD_CONSTRAINT_POLICY row that the rules read."""
    return HardRulePolicy(
        require_active_staff=policy.require_active_staff,
        prevent_shift_conflict=policy.prevent_shift_conflict,
        require_matching_role=policy.require_matching_role,
        require_matching_skill=policy.require_matching_skill,
        preserve_source_ward_minimum=policy.preserve_source_ward_minimum,
        preserve_minimum_staffing=policy.preserve_minimum_staffing,
        minimum_rest_hours=policy.minimum_rest_hours,
        maximum_daily_hours=policy.maximum_daily_hours,
        maximum_weekly_hours=policy.maximum_weekly_hours,
        maximum_consecutive_shifts=policy.maximum_consecutive_shifts,
    )


def lock_staff(db: Session, staff_ids: Collection[int]) -> None:
    """Lock the STAFF rows in ID order until the transaction ends (workflow.md 6.7, 6.11).

    Whoever is about to count the offers of these people takes this lock first,
    so two cases never count a shared candidate at the same moment.
    FOR NO KEY UPDATE, like the orchestrator: an insert with a foreign key to
    STAFF holds KEY SHARE, which FOR UPDATE would block.
    """
    if not staff_ids:
        return
    db.execute(
        select(Staff.id)
        .where(Staff.id.in_(staff_ids))
        .order_by(Staff.id)
        .with_for_update(key_share=True)
    )


def check_staff(
    db: Session, *, shift: Shift, staff_ids: Collection[int]
) -> dict[int, CandidateCheck]:
    """Check people nobody selected yet (the Solver's pool), keyed by staff ID."""
    return _check(db, shift, dict.fromkeys(staff_ids, _NO_TARGETS))


def check_items(
    db: Session, *, shift: Shift, items: Sequence[CandidateItem]
) -> dict[int, CandidateCheck]:
    """Check plan items against their CANDIDATE_ITEM_TARGET rows, keyed by item ID.

    For wave selection and Safety. Every item must propose `shift`.
    """
    for item in items:
        if item.proposed_shift_id != shift.id:
            raise ValueError(
                f"Candidate item {item.id} proposes shift {item.proposed_shift_id}, "
                f"not shift {shift.id}"
            )
    if len({item.staff_id for item in items}) != len(items):
        raise ValueError("Two items of the same staff member")
    with db.no_autoflush:
        targets = _item_targets(db, [item.id for item in items])
    checks = _check(db, shift, {item.staff_id: targets[item.id] for item in items})
    return {item.id: checks[item.staff_id] for item in items}


def _check(db: Session, shift: Shift, targets: Mapping[int, _Targets]) -> dict[int, CandidateCheck]:
    if not targets:
        return {}
    staff_ids = sorted(targets)
    proposed = ShiftSlot(shift.id, shift.start_at, shift.end_at)
    with db.no_autoflush:
        policy = to_policy(policy_service.get_hard_constraint_policy(db))
        requirement_roles = frozenset(
            requirement_service.get_current_requirement(db, shift.id).required_roles
        )
        staff = {
            staff_id: (status, role_id)
            for staff_id, status, role_id in db.execute(
                select(Staff.id, Staff.status, Staff.role_id).where(Staff.id.in_(staff_ids))
            )
        }
        missing = set(staff_ids) - set(staff)
        if missing:
            raise LookupError(f"No staff {sorted(missing)}")
        skills = gap_service.load_skill_sets(db, set(staff_ids))
        roster = _roster(db, staff_ids, proposed, policy)
        unavailability = _unavailability(db, staff_ids, proposed)

    checks: dict[int, CandidateCheck] = {}
    for staff_id in staff_ids:
        status, role_id = staff[staff_id]
        context = CandidateContext(
            staff_id=staff_id,
            status=status,
            role_id=role_id,
            skill_ids=skills.get(staff_id, frozenset()),
            proposed_shift=proposed,
            roster=tuple(roster.get(staff_id, ())),
            unavailability=tuple(unavailability.get(staff_id, ())),
            target_role_ids=targets[staff_id].role_ids or requirement_roles,
            target_skill_ids=targets[staff_id].skill_ids,
        )
        checks[staff_id] = CandidateCheck(context=context, result=evaluate(context, policy))
    return checks


def _roster(
    db: Session, staff_ids: Sequence[int], proposed: ShiftSlot, policy: HardRulePolicy
) -> dict[int, list[RosterEntry]]:
    """Roster rows of every status that can matter to a rule, keyed by staff ID.

    The window is the Asia/Bangkok week of the proposed shift plus a margin on
    both sides. The margin holds a run two shifts longer than the policy allows
    when no shift is longer than 24 hours. So every candidate that passes is
    counted exactly, and a longer run still fails.
    """
    week = week_start(proposed.start_at)
    margin = (policy.maximum_consecutive_shifts + 2) * (MAX_REST_WITHIN_RUN + _LONGEST_SHIFT)
    rows = db.execute(
        select(
            RosterAssignment.staff_id,
            RosterAssignment.status,
            Shift.id,
            Shift.start_at,
            Shift.end_at,
        )
        .join(Shift, Shift.id == RosterAssignment.shift_id)
        .where(
            RosterAssignment.staff_id.in_(staff_ids),
            Shift.end_at > week - margin,
            Shift.start_at < week + timedelta(days=7) + margin,
        )
        .order_by(RosterAssignment.id)
    )
    roster: dict[int, list[RosterEntry]] = {}
    for staff_id, status, shift_id, start_at, end_at in rows:
        roster.setdefault(staff_id, []).append(
            RosterEntry(ShiftSlot(shift_id, start_at, end_at), status)
        )
    return roster


def _unavailability(
    db: Session, staff_ids: Sequence[int], proposed: ShiftSlot
) -> dict[int, list[UnavailabilityPeriod]]:
    """The periods that overlap the proposed shift. No end_at = from start_at on."""
    rows = db.execute(
        select(
            StaffUnavailability.staff_id, StaffUnavailability.start_at, StaffUnavailability.end_at
        )
        .where(
            StaffUnavailability.staff_id.in_(staff_ids),
            StaffUnavailability.start_at < proposed.end_at,
            or_(
                StaffUnavailability.end_at.is_(None),
                StaffUnavailability.end_at > proposed.start_at,
            ),
        )
        .order_by(StaffUnavailability.id)
    )
    periods: dict[int, list[UnavailabilityPeriod]] = {}
    for staff_id, start_at, end_at in rows:
        periods.setdefault(staff_id, []).append(UnavailabilityPeriod(start_at, end_at))
    return periods


def _item_targets(db: Session, item_ids: Sequence[int]) -> dict[int, _Targets]:
    roles: dict[int, set[int]] = {}
    skills: dict[int, set[int]] = {}
    if item_ids:
        rows = db.execute(
            select(
                CandidateItemTarget.candidate_item_id,
                CandidateItemTarget.target_type,
                CandidateItemTarget.role_id,
                CandidateItemTarget.skill_id,
            ).where(CandidateItemTarget.candidate_item_id.in_(item_ids))
        )
        for item_id, target_type, role_id, skill_id in rows:
            if target_type is TargetType.ROLE and role_id is not None:
                roles.setdefault(item_id, set()).add(role_id)
            elif target_type is TargetType.SKILL and skill_id is not None:
                skills.setdefault(item_id, set()).add(skill_id)
    return {
        item_id: _Targets(
            role_ids=frozenset(roles.get(item_id, ())),
            skill_ids=frozenset(skills.get(item_id, ())),
        )
        for item_id in item_ids
    }
