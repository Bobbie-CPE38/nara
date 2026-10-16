from dataclasses import dataclass
from datetime import datetime

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
    # Effective roster interval: actual times, else the shift times (round 4
    # PR T2). None covers from the shift start or until the shift end
    start_at: datetime | None = None
    end_at: datetime | None = None
