"""Select Wave members from the immutable plan (workflow.md 6.6).

The handler owns OFFER_SENT and MANUAL_HANDOFF. No commit or case-status write.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, aliased

from app.core import clock
from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidateItemTarget,
    CandidateOutreach,
    CandidatePlan,
    RosterAssignment,
    Shift,
)
from app.domain.constraints.codes import OFFER_LIMIT_REACHED, SOURCE_SHIFT_TAKEN
from app.domain.enums import (
    COVERING_ROSTER_STATUSES,
    ManualHandoffReason,
    OutreachStatus,
)
from app.domain.staffing.wave_targets import (
    Slice,
    TargetCredit,
    covers,
    elementary_slices,
    fill_targets_by_slice,
    is_short,
)
from app.domain.workflow.case_status import GapFiller
from app.services import (
    availability_service,
    case_facts_service,
    gap_service,
    hard_rule_service,
    outreach_limit_service,
)
from app.services.optimization_service import record_item_targets
from app.services.outreach_attempt_service import contactable_item


@dataclass(frozen=True)
class WaveSelection:
    items: tuple[CandidateItem, ...]
    skipped: tuple[dict[str, int | str], ...]
    wave: int
    # Set when an outreach limit of the case stops every new wave (6.36.8); items is empty
    stopped: ManualHandoffReason | None = None


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


def _source_shift_ids(db: Session, item_ids: list[int]) -> dict[int, int]:
    """Item ID to the shift its source assignment sits on, for items that move someone."""
    if not item_ids:
        return {}
    return {
        item_id: shift_id
        for item_id, shift_id in db.execute(
            select(CandidateItem.id, RosterAssignment.shift_id)
            .join(RosterAssignment, RosterAssignment.id == CandidateItem.source_assignment_id)
            .where(CandidateItem.id.in_(item_ids))
        )
    }


def _taken_source_shifts(db: Session, case_id: int) -> dict[int, set[int]]:
    """Source shift ID to the staff holding it for this case (workflow.md 6.19).

    A staff member holds a source shift while their move has a live offer (SENT, not overdue),
    a pending approval request (ACCEPTED) or is done (a destination row linked to
    the source row). Only one person may be moved out of a source shift per case.
    """
    taken: dict[int, set[int]] = {}
    for shift_id, staff_id in db.execute(
        select(RosterAssignment.shift_id, CandidateItem.staff_id)
        .join(CandidateItem, CandidateItem.source_assignment_id == RosterAssignment.id)
        .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
        .where(
            CandidateOutreach.case_id == case_id,
            # An overdue SENT offer holds nothing, like in the case facts; the timeout
            # job still ends it. An ACCEPTED one is a commitment until it is decided.
            or_(
                CandidateOutreach.status == OutreachStatus.ACCEPTED,
                (CandidateOutreach.status == OutreachStatus.SENT)
                & (CandidateOutreach.expires_at > clock.now()),
            ),
        )
    ):
        taken.setdefault(shift_id, set()).add(staff_id)
    # A move done for this case: its approved request's item names the source row,
    # and the destination row links to that row. The destination shift alone would
    # also match the moves of an earlier case on the same shift.
    source = aliased(RosterAssignment)
    for shift_id, staff_id in db.execute(
        select(source.shift_id, RosterAssignment.staff_id)
        .join(source, source.id == RosterAssignment.transferred_from_assignment_id)
        .join(CandidateItem, CandidateItem.source_assignment_id == source.id)
        .join(ApprovalRequest, ApprovalRequest.candidate_item_id == CandidateItem.id)
        .where(
            ApprovalRequest.case_id == case_id,
            ApprovalRequest.is_approved.is_(True),
            CandidateItem.staff_id == RosterAssignment.staff_id,
            RosterAssignment.status.in_(list(COVERING_ROSTER_STATUSES)),
        )
    ):
        taken.setdefault(shift_id, set()).add(staff_id)
    return taken


def _open_gap(
    slices: list[Slice] | None,
    counted: list[GapFiller],
    kept: list[CandidateItem],
    candidates: list[CandidateItem],
    credits: dict[int, tuple[TargetCredit, ...]],
    person: Callable[[CandidateItem], GapFiller],
) -> int:
    """People still missing (headcount, roles, skills over all slices) after a selection."""
    chosen = [
        *counted,
        *(person(item) for item in kept),
        *(person(item) for item in candidates if item.staff_id in credits),
    ]
    missing = 0
    for piece in slices or []:
        present = [p for p in chosen if covers(p, piece.start_at, piece.end_at)]
        missing += max(0, piece.headcount_gap - len(present))
        for role_id, gap in piece.role_gaps.items():
            missing += max(0, gap - sum(1 for p in present if p.role_id == role_id))
        for skill_id, gap in piece.skill_gaps.items():
            missing += max(0, gap - sum(1 for p in present if skill_id in p.skill_ids))
    return missing


def select_wave(db: Session, *, case_id: int, shift: Shift) -> WaveSelection:
    # Round 6 PR EV6 (6.36.8): past the case's last wave or its deadline nobody is chosen
    stopped = outreach_limit_service.stop_reason(db, case_id)
    if stopped is not None:
        return WaveSelection((), (), outreach_limit_service.waves_sent(db, case_id) + 1, stopped)
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
    contactable = set(
        db.scalars(
            select(CandidateItem.id).where(
                CandidateItem.id.in_([item.id for item in items]), contactable_item(case_id)
            )
        )
    )
    remaining = [item for item in items if item.id in contactable]
    checks = hard_rule_service.check_items(db, shift=shift, items=remaining)
    limited = availability_service.staff_at_offer_limit(db, [item.staff_id for item in remaining])
    source_shift_of = _source_shift_ids(db, [item.id for item in remaining])
    taken = _taken_source_shifts(db, case_id)
    skipped: list[dict[str, int | str]] = []
    eligible: list[CandidateItem] = []
    for item in remaining:
        failures = checks[item.id].result.failed_rules
        source_shift_id = source_shift_of.get(item.id)
        reason: str | None
        if failures:
            reason = failures[0].value
        elif source_shift_id is not None and taken.get(source_shift_id, set()) - {item.staff_id}:
            reason = SOURCE_SHIFT_TAKEN
        elif item.staff_id in limited:
            reason = OFFER_LIMIT_REACHED
        else:
            reason = None
        if reason is None:
            eligible.append(item)
        else:
            skipped.append({"staff_id": item.staff_id, "reason": reason})

    # First contacts that can be sent now take priority over retries. Blocked
    # first contacts do not strand the retry queue. Rank within each phase stays fixed.
    first_contacts = [item for item in eligible if item.staff_id not in contacted_staff_ids]
    if first_contacts:
        eligible = first_contacts
    gap = gap_service.get_case_gap(db, case_id)
    fillers = case_facts_service.get_case_fillers(db, case_id, include_reserves=True)

    def person(item: CandidateItem) -> GapFiller:
        context = checks[item.id].context
        return GapFiller(
            item.staff_id,
            context.role_id,
            context.skill_ids,
            start_at=item.cover_start_at,
            end_at=item.cover_end_at,
        )

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
    # Per time slice: the people who cover the whole of a slice count there (round 4 PR T4)
    slices = elementary_slices(
        [interval for interval in gap.intervals if is_short(interval)],
        [*fillers, *(person(item) for item in eligible), *(person(item) for item in kept)],
    )
    # One person per source shift in a wave. The Solver's group already obeys it, so
    # its source shifts are closed to the others. Among the rest, exclusivity is
    # settled with the targets: when two chosen people share a source shift, keep
    # the one whose choice leaves the least of the gap open (rank order breaks ties).
    closed = {source_shift_of[item.id] for item in kept if item.id in source_shift_of}
    for item in candidates:
        if source_shift_of.get(item.id) in closed:
            skipped.append({"staff_id": item.staff_id, "reason": SOURCE_SHIFT_TAKEN})
    candidates = [item for item in candidates if source_shift_of.get(item.id) not in closed]
    dropped: set[int] = set()

    def fill(excluded: set[int]) -> dict[int, tuple[TargetCredit, ...]]:
        return fill_targets_by_slice(
            slices=slices,
            candidates=[person(item) for item in candidates if item.id not in excluded],
            already_selected=[person(item) for item in kept],
            counted=fillers,
        )

    def chosen_by_source(credit_map: dict[int, tuple[TargetCredit, ...]]) -> dict[int, list[int]]:
        groups: dict[int, list[int]] = {}
        for item in candidates:
            source_shift_id = source_shift_of.get(item.id)
            if item.staff_id in credit_map and source_shift_id is not None:
                groups.setdefault(source_shift_id, []).append(item.id)
        return groups

    credits = fill(dropped)
    while True:
        conflict = next((ids for ids in chosen_by_source(credits).values() if len(ids) > 1), None)
        if conflict is None:
            break
        best: tuple[int, set[int], dict[int, tuple[TargetCredit, ...]]] | None = None
        for keeper in conflict:
            trial_dropped = dropped | (set(conflict) - {keeper})
            trial = fill(trial_dropped)
            open_gap = _open_gap(slices, fillers, kept, candidates, trial, person)
            if best is None or open_gap < best[0]:
                best = (open_gap, trial_dropped, trial)
        assert best is not None
        _, dropped, credits = best
    for item in candidates:
        if item.id in dropped:
            skipped.append({"staff_id": item.staff_id, "reason": SOURCE_SHIFT_TAKEN})
    candidates = [item for item in candidates if item.id not in dropped]
    for item in candidates:
        if item.staff_id in credits:
            # Uncontacted Solver members may be selected for different targets in
            # a later wave. Replace their provisional credits before first send;
            # targets of anyone already contacted remain immutable.
            if item.id in target_item_ids and item.id not in contacted_item_ids:
                db.execute(
                    delete(CandidateItemTarget).where(
                        CandidateItemTarget.candidate_item_id == item.id
                    )
                )
            if item.id not in contacted_item_ids:
                record_item_targets(db, item, credits[item.staff_id])
    chosen = [item for item in eligible if item in kept or item.staff_id in credits]
    # Every new wave writes its number on all OFFER_SENT audit rows in the
    # same transaction as the offers (outreach_limit_service.waves_sent)
    wave = outreach_limit_service.waves_sent(db, case_id) + 1
    return WaveSelection(tuple(chosen), tuple(skipped), wave)
