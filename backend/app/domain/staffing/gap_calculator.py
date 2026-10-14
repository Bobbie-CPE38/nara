"""Shared gap calculation for event intake and ASSESSING (workflow.md sections 3, 8).

No database access, clock reads, or writes. Callers supply the stored headcount
requirement (required_staff and minimum_staff of STAFFING_REQUIREMENTS), the
preserve_minimum_staffing flag of the hard policy, role/skill requirements and
complete roster snapshots. They own persistence and audit logging.

required_staff is the workload target ceil(patient_count / patients_per_nurse).
It is written by the code that owns STAFFING_REQUIREMENTS (the seed, and the
merge window close) through required_staff_for(); the gap never recomputes it
from the patient count.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from math import ceil
from types import MappingProxyType

from app.domain.enums import COVERING_ROSTER_STATUSES
from app.domain.staffing.coverage import RosterMember


@dataclass(frozen=True)
class CountGap:
    """Counts needed by STAFFING_GAP_ROLE and STAFFING_GAP_SKILL."""

    required_count: int
    current_count: int

    @property
    def gap_count(self) -> int:
        return max(self.required_count - self.current_count, 0)


@dataclass(frozen=True)
class GapResult:
    # The headcount target this gap was measured against (workflow.md section 3.6)
    effective_minimum: int
    headcount_gap: int
    role_gaps: Mapping[int, CountGap]
    skill_gaps: Mapping[int, CountGap]

    def __post_init__(self) -> None:
        # Copy first: a read-only view of a caller-owned dict would still change
        # when that caller mutates the original dict.
        object.__setattr__(self, "role_gaps", MappingProxyType(dict(self.role_gaps)))
        object.__setattr__(self, "skill_gaps", MappingProxyType(dict(self.skill_gaps)))

    def __hash__(self) -> int:
        # MappingProxyType is not hashable on Python 3.11. Ignore insertion order
        # to match mapping equality, and hash the immutable CountGap values.
        return hash(
            (
                self.effective_minimum,
                self.headcount_gap,
                frozenset(self.role_gaps.items()),
                frozenset(self.skill_gaps.items()),
            )
        )

    @property
    def has_gap(self) -> bool:
        """A role or skill shortage also matters when total headcount is sufficient."""
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


def calculate_gap(
    *,
    shift_id: int,
    required_staff: int,
    minimum_staff: int,
    preserve_minimum_staffing: bool,
    required_roles: Mapping[int, int],
    required_skills: Mapping[int, int],
    roster: Iterable[RosterMember],
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

    Repeated assignments for the same person count once. Conflicting role/skill
    snapshots for that person raise ValueError instead of depending on input order.
    """
    effective_minimum = effective_minimum_for(
        required_staff=required_staff,
        minimum_staff=minimum_staff,
        preserve_minimum_staffing=preserve_minimum_staffing,
    )
    if any(count < 0 for count in (*required_roles.values(), *required_skills.values())):
        raise ValueError("Requirement counts must be non-negative")

    assigned: dict[int, RosterMember] = {}
    for member in roster:
        if member.shift_id != shift_id or member.status not in COVERING_ROSTER_STATUSES:
            continue
        previous = assigned.get(member.staff_id)
        if previous is not None and previous != member:
            raise ValueError(f"Conflicting coverage for staff_id={member.staff_id}")
        assigned[member.staff_id] = member

    roles = Counter(member.role_id for member in assigned.values())
    skills = Counter(skill_id for member in assigned.values() for skill_id in member.skill_ids)
    return GapResult(
        effective_minimum=effective_minimum,
        headcount_gap=max(effective_minimum - len(assigned), 0),
        role_gaps={
            role_id: CountGap(required, roles[role_id])
            for role_id, required in required_roles.items()
        },
        skill_gaps={
            skill_id: CountGap(required, skills[skill_id])
            for skill_id, required in required_skills.items()
        },
    )
