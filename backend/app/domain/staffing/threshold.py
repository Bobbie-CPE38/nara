"""Threshold of one event at a merge window close (docs/workflow.md, section 3.3).

An event passes when the shift, as it is right after that event, has a patient
ratio above the limit or is short of a required role or skill. Only a window
with a passing event writes required_staff and can open a case.

minimum_staff is not looked at here on purpose: a shift below its floor whose
ratio still holds and whose roles and skills are covered does not pass. The
floor only raises the headcount gap after the threshold has passed.

No database access, clock reads, or writes.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import RosterStatus
from app.domain.staffing.coverage import RosterMember


@dataclass(frozen=True)
class ThresholdResult:
    """Why an event passed. All empty and False = it did not pass."""

    ratio_exceeded: bool
    # IDs of the required roles and skills the shift has too few people for, sorted
    short_role_ids: tuple[int, ...]
    short_skill_ids: tuple[int, ...]

    @property
    def passed(self) -> bool:
        return self.ratio_exceeded or bool(self.short_role_ids) or bool(self.short_skill_ids)


def check_threshold(
    *,
    patient_count: int,
    patients_per_nurse: Decimal | int,
    required_roles: Mapping[int, int],
    required_skills: Mapping[int, int],
    roster: Iterable[RosterMember],
) -> ThresholdResult:
    """Judge a shift by its patient ratio and its role and skill requirements.

    The ratio is written as a multiplication, patient_count > ratio * staff,
    because a shift with nobody left would divide by zero. It gives the same
    answer as staff < ceil(patient_count / ratio).

    Only ASSIGNED roster rows count, each person once, like gap_calculator.
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

    people = {
        member.staff_id: member for member in roster if member.status is RosterStatus.ASSIGNED
    }
    roles = Counter(member.role_id for member in people.values())
    skills = Counter(skill_id for member in people.values() for skill_id in member.skill_ids)
    return ThresholdResult(
        ratio_exceeded=patient_count > ratio * len(people),
        short_role_ids=tuple(
            sorted(role_id for role_id, count in required_roles.items() if roles[role_id] < count)
        ),
        short_skill_ids=tuple(
            sorted(
                skill_id for skill_id, count in required_skills.items() if skills[skill_id] < count
            )
        ),
    )
