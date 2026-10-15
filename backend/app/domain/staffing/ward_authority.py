"""Which ward a head nurse may act on (docs/workflow.md section 6.12, R2-Q21).

One definition for approval decisions and the manual exits of MANUAL_HANDOFF.
manages_ward checks staff membership; can_decide checks the human actor role,
ward and Supervisor waiting condition.
"""

from app.core.constants import HEAD_NURSE_ROLE, SUPERVISOR_ROLE


def manages_ward(*, home_ward_id: int, ward_id: int) -> bool:
    """A head nurse acts only on shifts of their own ward."""
    return home_ward_id == ward_id


def can_decide(*, role: str | None, home_ward_id: int | None, ward_id: int, waited: bool) -> bool:
    """Shared human authority: own-ward Head Nurse or Supervisor after the delay.

    MANUAL_HANDOFF callers pass waited=True: Supervisor has immediate authority
    there. This does not grant Supervisor other Head Nurse operations.
    """
    return (role == HEAD_NURSE_ROLE and home_ward_id == ward_id) or (
        role == SUPERVISOR_ROLE and waited
    )
