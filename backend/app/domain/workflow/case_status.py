"""Case status computed from the remaining gap (docs/workflow.md, sections 4.2 and 5.3).

A case no longer follows one candidate. After every answer, approval decision or
offer timeout the orchestrator asks: is the gap of the case closed, and by whom?

No database access, clock reads, or writes. case_facts_service loads the rows and
builds the inputs, the same way gap_service does for gap_calculator.

MANUAL_HANDOFF and T7 are not decided here. Only the contact_candidate handler
can tell that no candidate is left, because it has to check the Hard Rules first.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.domain.enums import CaseStatus


@dataclass(frozen=True)
class GapNeeds:
    """What the case has to fill, from its STAFFING_GAP.

    role_gaps and skill_gaps map an ID to the number of people still missing.
    Entries with zero are allowed and ask for nothing.
    """

    headcount_gap: int
    role_gaps: Mapping[int, int]
    skill_gaps: Mapping[int, int]

    def __post_init__(self) -> None:
        # Copy first: a read-only view of a caller-owned dict would still change
        # when that caller mutates the original dict.
        object.__setattr__(self, "role_gaps", MappingProxyType(dict(self.role_gaps)))
        object.__setattr__(self, "skill_gaps", MappingProxyType(dict(self.skill_gaps)))
        if self.headcount_gap < 0:
            raise ValueError("Headcount gap must be non-negative")
        if any(count < 0 for count in (*self.role_gaps.values(), *self.skill_gaps.values())):
            raise ValueError("Gap counts must be non-negative")

    def __hash__(self) -> int:
        # MappingProxyType is not hashable on Python 3.11
        return hash(
            (
                self.headcount_gap,
                frozenset(self.role_gaps.items()),
                frozenset(self.skill_gaps.items()),
            )
        )


@dataclass(frozen=True)
class GapFiller:
    """One person counted toward the gap of a case, with their role and full skill set."""

    staff_id: int
    role_id: int
    skill_ids: frozenset[int]


def gap_closed(needs: GapNeeds, fillers: Iterable[GapFiller]) -> bool:
    """True when the group brings every gap of the case to zero.

    One person counts once toward headcount, once toward their role and once
    toward each skill they hold, like the roster in gap_calculator. The group
    as a whole must cover the gap; no single person has to (Q46, Q55).

    Repeated entries for the same person count once. Conflicting role or skill
    snapshots for that person raise ValueError instead of depending on input order.
    """
    people: dict[int, GapFiller] = {}
    for filler in fillers:
        previous = people.setdefault(filler.staff_id, filler)
        if previous != filler:
            raise ValueError(f"Conflicting coverage for staff_id={filler.staff_id}")

    roles = Counter(person.role_id for person in people.values())
    skills = Counter(skill_id for person in people.values() for skill_id in person.skill_ids)
    return (
        len(people) >= needs.headcount_gap
        and all(roles[role_id] >= count for role_id, count in needs.role_gaps.items())
        and all(skills[skill_id] >= count for skill_id, count in needs.skill_gaps.items())
    )


@dataclass(frozen=True)
class CaseFacts:
    """The three answers decide_status() needs.

    gap_closed_by_assigned: the people this case already put on the roster close
        the gap.
    gap_closed_with_pending: those people plus the candidates waiting for
        approval close the gap.
    has_open_offer: the case has an offer a candidate can accept right now. An
        offer that is SENT but paused, because its candidate accepted another
        case and is waiting for the outcome, does not count (Q29).

    There is no fact for "a pending approval can still fill the gap": waiting for
    approval does not stop the next wave. contact_candidate checks that itself
    when no candidate is left (T7).
    """

    gap_closed_by_assigned: bool
    gap_closed_with_pending: bool
    has_open_offer: bool

    def __post_init__(self) -> None:
        # The pending group contains the assigned group, so it cannot cover less
        if self.gap_closed_by_assigned and not self.gap_closed_with_pending:
            raise ValueError(
                "A gap closed by the assigned staff is also closed with the pending ones"
            )


def decide_status(facts: CaseFacts) -> CaseStatus:
    """The status a case should have. The first rule that holds is the answer.

    1. Assigned staff close the gap           -> EXECUTING (then RESOLVED)
    2. Assigned plus pending close the gap    -> WAITING_APPROVAL
    3. The case has an open offer             -> WAITING_RESPONSE
    4. Otherwise                              -> OUTREACH (send the next wave)
    """
    if facts.gap_closed_by_assigned:
        return CaseStatus.EXECUTING
    if facts.gap_closed_with_pending:
        return CaseStatus.WAITING_APPROVAL
    if facts.has_open_offer:
        return CaseStatus.WAITING_RESPONSE
    return CaseStatus.OUTREACH
