from dataclasses import dataclass

from app.domain.enums import RosterStatus


@dataclass(frozen=True)
class RosterMember:
    """One roster assignment with the staff member's role and complete skill set.

    Callers load and join the database records before constructing these values.
    Employment status and home ward do not determine coverage: assignment to the
    target shift does, including replacements from another ward.
    The staff-deactivation flow must cancel future assignments when setting
    INACTIVE; require_active_staff governs candidate eligibility. That flow is
    a caller responsibility, not implemented by this coverage snapshot.
    """

    staff_id: int
    shift_id: int
    status: RosterStatus
    role_id: int
    skill_ids: frozenset[int]
