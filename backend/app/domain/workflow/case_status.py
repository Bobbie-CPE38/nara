"""Case status computed from the remaining gap (docs/workflow.md, sections 4.2 and 5.3).

A case no longer follows one candidate. After every answer, approval decision or
offer timeout the orchestrator asks: is the gap of the case closed, and if not,
is there something to wait for or someone left to contact?

No database access, clock reads, or writes. case_facts_service loads the rows and
builds the inputs, the same way gap_service does for gap_calculator.

MANUAL_HANDOFF is not decided here. Only the contact_candidate handler can tell
that nobody can be contacted, because it has to check the Hard Rules first. When
nothing is left to wait for, decide_status() sends the case to OUTREACH and that
handler stops it (T5).
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import MappingProxyType

from app.domain.enums import CaseStatus


@dataclass(frozen=True)
class GapFiller:
    """One person counted toward the gap of a case, with their role and full skill set.

    Not RosterMember: that one is a roster row and carries a shift and a status,
    which a candidate still waiting for approval does not have.

    start_at/end_at is the time the person covers: the roster interval once
    assigned, the cover window of the candidate item while pending (round 4
    PR T3). None covers from the shift start or until the shift end. One person
    with two intervals is two fillers with the same staff_id.
    """

    staff_id: int
    role_id: int
    skill_ids: frozenset[int]
    start_at: datetime | None = None
    end_at: datetime | None = None


@dataclass(frozen=True)
class IntervalGap:
    """What one time slice of a case gap still misses (round 4 PR T3).

    role_gaps and skill_gaps hold only the short roles and skills, like CaseGap.
    """

    start_at: datetime
    end_at: datetime
    headcount_gap: int
    role_gaps: Mapping[int, int] = field(default_factory=dict)
    skill_gaps: Mapping[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.start_at >= self.end_at:
            raise ValueError("A gap slice must start before it ends")
        object.__setattr__(self, "role_gaps", MappingProxyType(dict(self.role_gaps)))
        object.__setattr__(self, "skill_gaps", MappingProxyType(dict(self.skill_gaps)))


def remaining_intervals(
    intervals: Iterable[IntervalGap], from_at: datetime
) -> tuple[IntervalGap, ...]:
    """The part of each slice from `from_at` on, with its counts (round 4 PR C3).

    A slice over by then is dropped, one that has started is cut at `from_at`.
    """
    return tuple(
        replace(interval, start_at=max(interval.start_at, from_at))
        for interval in intervals
        if interval.end_at > from_at
    )


def intervals_closed(intervals: Iterable[IntervalGap], fillers: Iterable[GapFiller]) -> bool:
    """True when the fillers close every slice for the whole of that slice.

    Each slice is cut again wherever a filler starts or ends inside it, and every
    piece must pass gap_closed() with only the fillers present for that whole
    piece. Filling part of a slice, or one slice of two, does not close the gap
    (workflow.md 6.20): the summary counts never decide this.
    """
    people = list(fillers)
    for interval in intervals:
        cuts = {interval.start_at, interval.end_at}
        for filler in people:
            for point in (filler.start_at, filler.end_at):
                if point is not None and interval.start_at < point < interval.end_at:
                    cuts.add(point)
        points = sorted(cuts)
        for start, end in zip(points, points[1:], strict=False):
            present = [
                filler
                for filler in people
                if (filler.start_at is None or filler.start_at <= start)
                and (filler.end_at is None or filler.end_at >= end)
            ]
            if not gap_closed(
                headcount_gap=interval.headcount_gap,
                role_gaps=interval.role_gaps,
                skill_gaps=interval.skill_gaps,
                fillers=present,
            ):
                return False
    return True


def gap_closed(
    *,
    headcount_gap: int,
    role_gaps: Mapping[int, int],
    skill_gaps: Mapping[int, int],
    fillers: Iterable[GapFiller],
) -> bool:
    """True when the group brings every gap of the case to zero.

    role_gaps and skill_gaps map an ID to the number of people still missing; an
    entry with zero asks for nothing. One person counts once toward headcount,
    once toward their role and once toward each skill they hold, like the roster
    in gap_calculator. The group as a whole must cover the gap; no single person
    has to (Q46, Q55). A person listed twice counts once.
    """
    if headcount_gap < 0 or any(count < 0 for count in (*role_gaps.values(), *skill_gaps.values())):
        raise ValueError("Gap counts must be non-negative")
    people = {filler.staff_id: filler for filler in fillers}
    roles = Counter(person.role_id for person in people.values())
    skills = Counter(skill_id for person in people.values() for skill_id in person.skill_ids)
    return (
        len(people) >= headcount_gap
        and all(roles[role_id] >= count for role_id, count in role_gaps.items())
        and all(skills[skill_id] >= count for skill_id, count in skill_gaps.items())
    )


@dataclass(frozen=True, kw_only=True)
class CaseFacts:
    """The answers decide_status() needs.

    gap_closed_by_assigned: the people this case already put on the roster close
        the gap.
    gap_closed_with_pending: those people plus the candidates waiting for
        approval close the gap.
    has_open_offer: the case has an offer a candidate can accept right now. An
        offer that is SENT but paused, because its candidate accepted another
        case and is waiting for the outcome, does not count (Q29).
    has_uncontacted_candidate: the plan of the case still holds a candidate this
        case never sent an offer to.
    has_pending_approval: at least one candidate of the case waits for approval.
    has_paused_offer: the case has a SENT offer that is paused.

    The last three only matter while the gap is open and no offer is open. They
    tell a case with nobody left to contact whether it still has something to
    wait for, so it does not walk through OUTREACH on every recompute.
    """

    gap_closed_by_assigned: bool
    gap_closed_with_pending: bool
    has_open_offer: bool
    has_uncontacted_candidate: bool
    has_pending_approval: bool
    has_paused_offer: bool

    def __post_init__(self) -> None:
        # The pending group contains the assigned group, so it cannot cover less
        if self.gap_closed_by_assigned and not self.gap_closed_with_pending:
            raise ValueError(
                "A gap closed by the assigned staff is also closed with the pending ones"
            )


def decide_status(facts: CaseFacts) -> CaseStatus:
    """The status a case should have. The first rule that holds is the answer.

    1. Assigned staff close the gap              -> EXECUTING (then RESOLVED)
    2. Assigned plus pending close the gap       -> WAITING_APPROVAL
    3. The case has an open offer                -> WAITING_RESPONSE
    4. The plan has a candidate not yet contacted -> OUTREACH (send the next wave)
    5. A candidate waits for approval            -> WAITING_APPROVAL (keep waiting)
    6. The case has a paused offer               -> WAITING_RESPONSE (keep waiting)
    7. Otherwise                                 -> OUTREACH (the handler hands off)

    Rule 4 comes before 5 and 6: waiting for an approval or a paused offer never
    stops the next wave. Rules 5 and 6 are the order contact_candidate itself
    uses when it finds nobody to contact (T7, then the paused offer).
    """
    if facts.gap_closed_by_assigned:
        return CaseStatus.EXECUTING
    if facts.gap_closed_with_pending:
        return CaseStatus.WAITING_APPROVAL
    if facts.has_open_offer:
        return CaseStatus.WAITING_RESPONSE
    if facts.has_uncontacted_candidate:
        return CaseStatus.OUTREACH
    if facts.has_pending_approval:
        return CaseStatus.WAITING_APPROVAL
    if facts.has_paused_offer:
        return CaseStatus.WAITING_RESPONSE
    return CaseStatus.OUTREACH
