"""Shared policy selection for the single-policy walking skeleton.

Event intake, ASSESSING, optimization and safety use the seeded hospital-wide
hard policy (id=1), and optimization also uses the seeded soft policy (id=1).
No latest-version or wall-clock selection: policy activation and per-ward
overrides are future work. Callers must not edit a policy mid-case.
"""

from sqlalchemy.orm import Session

from app.db.models import HardConstraintPolicy, SoftConstraintPolicy


def get_hard_constraint_policy(db: Session) -> HardConstraintPolicy:
    """Read the demo policy without adding, flushing or committing anything."""
    policy = db.get(HardConstraintPolicy, 1)
    if policy is None:
        raise LookupError("Hard constraint policy id=1 is missing; load the demo seed")
    return policy


def get_soft_constraint_policy(db: Session) -> SoftConstraintPolicy:
    """Read the demo soft policy without adding, flushing or committing anything."""
    policy = db.get(SoftConstraintPolicy, 1)
    if policy is None:
        raise LookupError("Soft constraint policy id=1 is missing; load the demo seed")
    return policy
