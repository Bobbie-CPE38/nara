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
  * A candidate may cover only part of the shift (Cover) and may be moved out of
    another shift (its source assignment). The rules then judge the cover window
    against the roster as it will be after the move (see _apply_cover).
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NoReturn

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
from app.domain.enums import COMMITTED_ROSTER_STATUSES, TargetType
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


@dataclass(frozen=True)
class Cover:
    """The part of a shift a candidate covers, and the assignment they are moved out of.

    start_at and end_at are both None for the whole shift, both set for a window
    inside it. source_assignment_id is the roster row the candidate leaves, None
    when they are not moved. Planning passes it to check_staff and Safety reads it
    from the CANDIDATE_ITEM row, so both build the same context.
    """

    start_at: datetime | None
    end_at: datetime | None
    source_assignment_id: int | None

    def __post_init__(self) -> None:
        if (self.start_at is None) != (self.end_at is None):
            raise ValueError("A cover window needs both start_at and end_at, or neither")

    @classmethod
    def of(cls, item: CandidateItem) -> "Cover":
        return cls(item.cover_start_at, item.cover_end_at, item.source_assignment_id)


FULL_SHIFT = Cover(None, None, None)


@dataclass(frozen=True)
class _Subject:
    """What _check judges for one staff member: their targets and their cover."""

    targets: _Targets
    cover: Cover


@dataclass(frozen=True)
class _Row:
    """A loaded roster row with its ID, so a source assignment can be found."""

    assignment_id: int
    entry: RosterEntry


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
    db: Session,
    *,
    shift: Shift,
    staff_ids: Collection[int],
    covers: Mapping[int, Cover] | None = None,
) -> dict[int, CandidateCheck]:
    """Check people nobody selected yet (the Solver's pool), keyed by staff ID.

    `covers` gives the cover of a staff member who would take only part of the
    shift or be moved out of another shift; the others cover the whole shift.
    Safety later reads the same values from the item row via check_items.
    """
    covers = covers or {}
    return _check(
        db,
        shift,
        {
            staff_id: _Subject(_NO_TARGETS, covers.get(staff_id, FULL_SHIFT))
            for staff_id in staff_ids
        },
    )


def check_items(
    db: Session, *, shift: Shift, items: Sequence[CandidateItem]
) -> dict[int, CandidateCheck]:
    """Check plan items against their CANDIDATE_ITEM_TARGET rows, keyed by item ID.

    For wave selection and Safety. Every item must propose `shift`. The cover and
    the source assignment come from the item row, so Safety never computes a window.
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
    checks = _check(
        db, shift, {item.staff_id: _Subject(targets[item.id], Cover.of(item)) for item in items}
    )
    return {item.id: checks[item.staff_id] for item in items}


def _check(
    db: Session, shift: Shift, subjects: Mapping[int, _Subject]
) -> dict[int, CandidateCheck]:
    if not subjects:
        return {}
    staff_ids = sorted(subjects)
    full_shift = ShiftSlot(shift.id, shift.start_at, shift.end_at)
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
        roster = _roster(db, staff_ids, full_shift, policy)
        unavailability = _unavailability(db, staff_ids, full_shift)

        contexts: dict[int, CandidateContext] = {}
        for staff_id in staff_ids:
            status, role_id = staff[staff_id]
            subject = subjects[staff_id]
            proposed = _proposed_slot(shift, subject.cover)
            entries, linked_duty = _apply_cover(
                db, shift, proposed, subject.cover, staff_id, roster.get(staff_id, ())
            )
            contexts[staff_id] = CandidateContext(
                staff_id=staff_id,
                status=status,
                role_id=role_id,
                skill_ids=skills.get(staff_id, frozenset()),
                proposed_shift=proposed,
                roster=entries,
                unavailability=tuple(unavailability.get(staff_id, ())),
                target_role_ids=subject.targets.role_ids or requirement_roles,
                target_skill_ids=subject.targets.skill_ids,
                linked_duty=linked_duty,
            )

    return {
        staff_id: CandidateCheck(context=context, result=evaluate(context, policy))
        for staff_id, context in contexts.items()
    }


def _proposed_slot(shift: Shift, cover: Cover) -> ShiftSlot:
    """The window the candidate covers, which must lie inside the shift."""
    start_at = cover.start_at or shift.start_at
    end_at = cover.end_at or shift.end_at
    if not shift.start_at <= start_at < end_at <= shift.end_at:
        raise ValueError(
            f"Cover {start_at.isoformat()} to {end_at.isoformat()} is not inside shift {shift.id}"
        )
    return ShiftSlot(shift.id, start_at, end_at)


def _apply_cover(
    db: Session,
    shift: Shift,
    proposed: ShiftSlot,
    cover: Cover,
    staff_id: int,
    rows: Sequence[_Row],
) -> tuple[tuple[RosterEntry, ...], ShiftSlot | None]:
    """The roster as it will be once the candidate takes the cover, and the linked duty.

    Entries of the proposed shift are rewritten to the covered window. Rules read
    them only by shift_id, and CandidateContext allows one set of times per shift.

    With a source assignment the candidate leaves that row at the start of the
    cover. cut = the earlier of the source's end and the cover start:
      * cut at or before the source start: the whole source shift is given up, so
        its entries are dropped.
      * otherwise the source shift is cut to [source start, cut). It is the
        linked duty only when the cut meets the cover exactly; a gap leaves two
        separate duties that the rest rule judges as usual.
    A source row that is no longer committed (cancelled since planning) changes
    nothing and links nothing: raising would fail the whole case.
    """
    entries = [
        RosterEntry(proposed, row.entry.status)
        if row.entry.shift.shift_id == shift.id
        else row.entry
        for row in rows
    ]
    if cover.source_assignment_id is None:
        return tuple(entries), None

    source = next((row for row in rows if row.assignment_id == cover.source_assignment_id), None)
    if source is None:
        _refuse_source(db, cover.source_assignment_id, staff_id)
    source_slot = source.entry.shift
    if source_slot.shift_id == shift.id:
        raise ValueError(f"Source assignment {source.assignment_id} is on the proposed shift")
    if source.entry.status not in COMMITTED_ROSTER_STATUSES:
        return tuple(entries), None

    cut = min(source_slot.end_at, proposed.start_at)
    if cut <= source_slot.start_at:
        return tuple(e for e in entries if e.shift.shift_id != source_slot.shift_id), None
    kept = ShiftSlot(source_slot.shift_id, source_slot.start_at, cut)
    entries = [
        RosterEntry(kept, e.status) if e.shift.shift_id == source_slot.shift_id else e
        for e in entries
    ]
    return tuple(entries), (kept if cut == proposed.start_at else None)


def _refuse_source(db: Session, assignment_id: int, staff_id: int) -> NoReturn:
    """Raise for a source row the roster window did not return."""
    row = db.get(RosterAssignment, assignment_id)
    if row is None:
        raise LookupError(f"No roster assignment {assignment_id}")
    if row.staff_id != staff_id:
        raise ValueError(f"Assignment {assignment_id} belongs to staff {row.staff_id}")
    raise ValueError(f"Assignment {assignment_id} lies outside the roster window")


def _roster(
    db: Session, staff_ids: Sequence[int], proposed: ShiftSlot, policy: HardRulePolicy
) -> dict[int, list[_Row]]:
    """Roster rows of every status that can matter to a rule, keyed by staff ID.

    The window is the Asia/Bangkok week of the full shift (whatever part of it a
    candidate covers) plus a margin on both sides. The margin holds a run two
    shifts longer than the policy allows when no shift is longer than 24 hours.
    So every candidate that passes is counted exactly, and a longer run still
    fails. A CANCELLED row on the proposed shift makes the UNAVAILABLE rule fail.
    The row ID is kept so a source assignment can be found among the rows.
    """
    week = week_start(proposed.start_at)
    margin = (policy.maximum_consecutive_shifts + 2) * (MAX_REST_WITHIN_RUN + _LONGEST_SHIFT)
    rows = db.execute(
        select(
            RosterAssignment.id,
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
    roster: dict[int, list[_Row]] = {}
    for assignment_id, staff_id, status, shift_id, start_at, end_at in rows:
        roster.setdefault(staff_id, []).append(
            _Row(assignment_id, RosterEntry(ShiftSlot(shift_id, start_at, end_at), status))
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
