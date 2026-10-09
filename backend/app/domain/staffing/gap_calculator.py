"""Shared gap calculation for event intake and ASSESSING (workflow.md sections 3, 8).

No database access, clock reads, or writes. Callers supply patient count,
role/skill requirements and complete roster snapshots. The ratio comes from
HARD_CONSTRAINT_POLICY.maximum_patients_per_nurse via the shared policy service.
They own persistence and audit logging. Headcount is derived from patient workload,
not the stored required_staff or minimum_staff values.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from math import ceil
from types import MappingProxyType

from app.domain.enums import RosterStatus
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
    minimum_required_staff: int
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
                self.minimum_required_staff,
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


def calculate_gap(
    *,
    shift_id: int,
    patient_count: int,
    patients_per_nurse: Decimal | int,
    required_roles: Mapping[int, int],
    required_skills: Mapping[int, int],
    roster: Iterable[RosterMember],
) -> GapResult:
    """Compare distinct ASSIGNED staff against workload and role/skill requirements.

    minimum_required_staff = ceil(patient_count / patients_per_nurse).
    Event intake and ASSESSING both load the skeleton's hospital-wide policy with
    policy_service.get_hard_constraint_policy(db) and pass its
    maximum_patients_per_nurse. There is no fallback ratio in the calculator.
    The ratio must be a positive, finite Decimal or int; float and bool are rejected.
    Decimal supports non-integer ratios;
    exact rational division avoids floating-point or Decimal rounding at boundaries.

    Mapping keys are role/skill IDs and values are required counts. Results retain
    every required role and skill, including those with zero shortage, and clamp
    shortages at zero. A person counts once toward headcount and their role, and
    once toward each skill they possess; these gaps must not be summed together.

    Repeated assignments for the same person count once. Conflicting role/skill
    snapshots for that person raise ValueError instead of depending on input order.
    """
    if patient_count < 0:
        raise ValueError("Patient count must be non-negative")
    if isinstance(patients_per_nurse, bool) or not isinstance(patients_per_nurse, (Decimal, int)):
        raise TypeError("Patients per nurse must be a Decimal or int, not float or bool")
    ratio = Decimal(patients_per_nurse)
    if not ratio.is_finite() or ratio <= 0:
        raise ValueError("Patients per nurse must be positive and finite")
    if any(count < 0 for count in (*required_roles.values(), *required_skills.values())):
        raise ValueError("Requirement counts must be non-negative")

    assigned: dict[int, RosterMember] = {}
    for member in roster:
        if member.shift_id != shift_id or member.status != RosterStatus.ASSIGNED:
            continue
        previous = assigned.get(member.staff_id)
        if previous is not None and previous != member:
            raise ValueError(f"Conflicting coverage for staff_id={member.staff_id}")
        assigned[member.staff_id] = member

    roles = Counter(member.role_id for member in assigned.values())
    skills = Counter(skill_id for member in assigned.values() for skill_id in member.skill_ids)
    minimum_required_staff = ceil(Fraction(patient_count) / Fraction(ratio))
    return GapResult(
        minimum_required_staff=minimum_required_staff,
        headcount_gap=max(minimum_required_staff - len(assigned), 0),
        role_gaps={
            role_id: CountGap(required, roles[role_id])
            for role_id, required in required_roles.items()
        },
        skill_gaps={
            skill_id: CountGap(required, skills[skill_id])
            for skill_id, required in required_skills.items()
        },
    )
