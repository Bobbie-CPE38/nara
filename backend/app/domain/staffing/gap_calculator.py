"""Shared gap calculation for event intake and ASSESSING (workflow.md sections 3, 8).

No database access, clock reads, or writes. Callers supply the stored headcount
requirement (required_staff and minimum_staff of STAFFING_REQUIREMENTS), the
preserve_minimum_staffing flag of the hard policy, role/skill requirements and
complete roster snapshots. They own persistence and audit logging.

required_staff is the workload target ceil(patient_count / patients_per_nurse).
It is written by the code that owns STAFFING_REQUIREMENTS (the seed, and the
merge window close) through required_staff_for(); the gap never recomputes it
from the patient count.

Round 4 PR T3 (workflow.md 6.20): with a window, the gap is measured per time
slice from max(clock at assessment, shift start) to the shift end. Each person
counts only inside their own roster interval. The summary counts are the worst
slice of each dimension, never a sum across slices.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from math import ceil
from types import MappingProxyType

from app.domain.enums import COVERING_ROSTER_STATUSES
from app.domain.staffing.coverage import RosterMember

_Span = tuple[datetime | None, datetime | None]


@dataclass(frozen=True)
class CountGap:
    """Counts needed by STAFFING_GAP_ROLE and STAFFING_GAP_SKILL."""

    required_count: int
    current_count: int

    @property
    def gap_count(self) -> int:
        return max(self.required_count - self.current_count, 0)


@dataclass(frozen=True)
class GapInterval:
    """One time slice [start_at, end_at) of a gap: a row of each slice table."""

    start_at: datetime
    end_at: datetime
    headcount: CountGap
    role_gaps: Mapping[int, CountGap]
    skill_gaps: Mapping[int, CountGap]

    def __post_init__(self) -> None:
        object.__setattr__(self, "role_gaps", MappingProxyType(dict(self.role_gaps)))
        object.__setattr__(self, "skill_gaps", MappingProxyType(dict(self.skill_gaps)))

    def __hash__(self) -> int:
        return hash(
            (
                self.start_at,
                self.end_at,
                self.headcount,
                frozenset(self.role_gaps.items()),
                frozenset(self.skill_gaps.items()),
            )
        )

    @property
    def has_gap(self) -> bool:
        return (
            self.headcount.gap_count > 0
            or any(gap.gap_count > 0 for gap in self.role_gaps.values())
            or any(gap.gap_count > 0 for gap in self.skill_gaps.values())
        )


@dataclass(frozen=True)
class GapResult:
    # The headcount target this gap was measured against (workflow.md section 3.6)
    effective_minimum: int
    headcount_gap: int
    role_gaps: Mapping[int, CountGap]
    skill_gaps: Mapping[int, CountGap]
    # Start of the measured window; None when measured without one (whole shift)
    evaluated_from: datetime | None = None
    # Time slices in order. Empty without a window, or when no time is left
    intervals: tuple[GapInterval, ...] = ()

    def __post_init__(self) -> None:
        # Copy first: a read-only view of a caller-owned dict would still change
        # when that caller mutates the original dict.
        object.__setattr__(self, "role_gaps", MappingProxyType(dict(self.role_gaps)))
        object.__setattr__(self, "skill_gaps", MappingProxyType(dict(self.skill_gaps)))
        object.__setattr__(self, "intervals", tuple(self.intervals))

    def __hash__(self) -> int:
        # MappingProxyType is not hashable on Python 3.11. Ignore insertion order
        # to match mapping equality, and hash the immutable CountGap values.
        return hash(
            (
                self.effective_minimum,
                self.headcount_gap,
                frozenset(self.role_gaps.items()),
                frozenset(self.skill_gaps.items()),
                self.evaluated_from,
                self.intervals,
            )
        )

    @property
    def has_gap(self) -> bool:
        """A role or skill shortage also matters when total headcount is sufficient.

        With a window only the slices decide (workflow.md 6.20). An empty window
        has no slice and so no gap; gap_service never passes one, because a
        shift with no time left is measured whole, as before round 4.
        """
        if self.evaluated_from is not None:
            return any(interval.has_gap for interval in self.intervals)
        return (
            self.headcount_gap > 0
            or any(gap.gap_count > 0 for gap in self.role_gaps.values())
            or any(gap.gap_count > 0 for gap in self.skill_gaps.values())
        )


def required_staff_for(patient_count: int, patients_per_nurse: Decimal | int) -> int:
    """Workload headcount target: ceil(patient_count / patients_per_nurse).

    The ratio is HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse. It must be a
    positive, finite Decimal or int; float and bool are rejected. Decimal supports
    non-integer ratios; exact rational division avoids floating-point or Decimal
    rounding at boundaries. There is no fallback ratio.
    """
    if patient_count < 0:
        raise ValueError("Patient count must be non-negative")
    if isinstance(patients_per_nurse, bool) or not isinstance(patients_per_nurse, (Decimal, int)):
        raise TypeError("Patients per nurse must be a Decimal or int, not float or bool")
    ratio = Decimal(patients_per_nurse)
    if not ratio.is_finite() or ratio <= 0:
        raise ValueError("Patients per nurse must be positive and finite")
    return ceil(Fraction(patient_count) / Fraction(ratio))


def effective_minimum_for(
    *, required_staff: int, minimum_staff: int, preserve_minimum_staffing: bool
) -> int:
    """Headcount target of a shift (workflow.md section 3.6).

    With preserve_minimum_staffing the fixed floor minimum_staff also counts;
    without it only the workload target required_staff does.
    """
    if required_staff < 0 or minimum_staff < 0:
        raise ValueError("Staff counts must be non-negative")
    if preserve_minimum_staffing:
        return max(minimum_staff, required_staff)
    return required_staff


@dataclass(frozen=True)
class _Counter:
    """Counts one group of people against the fixed requirement of the shift."""

    effective_minimum: int
    required_roles: Mapping[int, int]
    required_skills: Mapping[int, int]

    def count(
        self, people: Iterable[RosterMember]
    ) -> tuple[CountGap, dict[int, CountGap], dict[int, CountGap]]:
        members = list(people)
        roles = Counter(member.role_id for member in members)
        skills = Counter(skill_id for member in members for skill_id in member.skill_ids)
        return (
            CountGap(self.effective_minimum, len(members)),
            {
                role_id: CountGap(required, roles[role_id])
                for role_id, required in self.required_roles.items()
            },
            {
                skill_id: CountGap(required, skills[skill_id])
                for skill_id, required in self.required_skills.items()
            },
        )


def calculate_gap(
    *,
    shift_id: int,
    required_staff: int,
    minimum_staff: int,
    preserve_minimum_staffing: bool,
    required_roles: Mapping[int, int],
    required_skills: Mapping[int, int],
    roster: Iterable[RosterMember],
    window: tuple[datetime, datetime] | None = None,
) -> GapResult:
    """Compare distinct covering staff against the headcount and role/skill requirements.

    Covering means ASSIGNED or COMPLETED (COVERING_ROSTER_STATUSES).

    effective_minimum = effective_minimum_for(...) and
    headcount_gap = max(effective_minimum - assigned staff, 0).
    Event intake and ASSESSING both pass required_staff and minimum_staff of the
    shift's current requirement and the flag of the hard policy loaded with
    policy_service.get_hard_constraint_policy(db).

    Mapping keys are role/skill IDs and values are required counts. Results retain
    every required role and skill, including those with zero shortage, and clamp
    shortages at zero. A person counts once toward headcount and their role, and
    once toward each skill they possess; these gaps must not be summed together.

    window = (evaluated_from, shift end) measures per time slice (round 4 PR T3).
    The window is cut at every start and end of a covering roster interval inside
    it, and neighbouring slices with the same counts are joined, so a shift where
    everyone works the whole shift has one slice. A member without an interval
    covers the whole window. The summary is the worst slice of each dimension.
    Without a window every covering row counts, as before round 4.

    Repeated assignments for the same person count once. Conflicting role/skill
    snapshots for that person raise ValueError instead of depending on input order.
    """
    counter = _Counter(
        effective_minimum=effective_minimum_for(
            required_staff=required_staff,
            minimum_staff=minimum_staff,
            preserve_minimum_staffing=preserve_minimum_staffing,
        ),
        required_roles=required_roles,
        required_skills=required_skills,
    )
    if any(count < 0 for count in (*required_roles.values(), *required_skills.values())):
        raise ValueError("Requirement counts must be non-negative")

    assigned: dict[int, RosterMember] = {}
    spans: dict[int, list[_Span]] = {}
    for member in roster:
        if member.shift_id != shift_id or member.status not in COVERING_ROSTER_STATUSES:
            continue
        previous = assigned.get(member.staff_id)
        if previous is not None and (previous.role_id, previous.skill_ids) != (
            member.role_id,
            member.skill_ids,
        ):
            raise ValueError(f"Conflicting coverage for staff_id={member.staff_id}")
        assigned[member.staff_id] = member
        spans.setdefault(member.staff_id, []).append((member.start_at, member.end_at))

    if window is None:
        headcount, role_gaps, skill_gaps = counter.count(assigned.values())
        return GapResult(
            effective_minimum=counter.effective_minimum,
            headcount_gap=headcount.gap_count,
            role_gaps=role_gaps,
            skill_gaps=skill_gaps,
        )

    intervals = _slices(window, assigned, spans, counter)
    if intervals:
        headcount = min((interval.headcount for interval in intervals), key=_present)
        role_gaps = {
            role_id: min((interval.role_gaps[role_id] for interval in intervals), key=_present)
            for role_id in required_roles
        }
        skill_gaps = {
            skill_id: min((interval.skill_gaps[skill_id] for interval in intervals), key=_present)
            for skill_id in required_skills
        }
    else:
        # No time left in the shift: keep the whole-shift count for display only.
        # has_gap is False, so no case opens and no gap row is written
        headcount, role_gaps, skill_gaps = counter.count(assigned.values())
    return GapResult(
        effective_minimum=counter.effective_minimum,
        headcount_gap=headcount.gap_count,
        role_gaps=role_gaps,
        skill_gaps=skill_gaps,
        evaluated_from=window[0],
        intervals=intervals,
    )


def _present(count: CountGap) -> int:
    # The required count is the same in every slice, so the fewest people
    # present is the largest gap of that dimension
    return count.current_count


def _slices(
    window: tuple[datetime, datetime],
    assigned: Mapping[int, RosterMember],
    spans: Mapping[int, list[_Span]],
    counter: _Counter,
) -> tuple[GapInterval, ...]:
    """Cut the window at every roster start or end inside it, then join equal neighbours."""
    start, end = window
    if start >= end:
        return ()
    cuts = {start, end}
    for member_spans in spans.values():
        for point in (point for span in member_spans for point in span):
            if point is not None and start < point < end:
                cuts.add(point)
    points = sorted(cuts)

    slices: list[GapInterval] = []
    for slice_start, slice_end in zip(points, points[1:], strict=False):
        present = [
            assigned[staff_id]
            for staff_id, member_spans in spans.items()
            if any(_covers(span, slice_start, slice_end) for span in member_spans)
        ]
        headcount, role_gaps, skill_gaps = counter.count(present)
        if slices and (slices[-1].headcount, slices[-1].role_gaps, slices[-1].skill_gaps) == (
            headcount,
            role_gaps,
            skill_gaps,
        ):
            slices[-1] = GapInterval(
                slices[-1].start_at, slice_end, headcount, role_gaps, skill_gaps
            )
        else:
            slices.append(GapInterval(slice_start, slice_end, headcount, role_gaps, skill_gaps))
    return tuple(slices)


def _covers(span: _Span, start: datetime, end: datetime) -> bool:
    span_start, span_end = span
    return (span_start is None or span_start <= start) and (span_end is None or span_end >= end)
