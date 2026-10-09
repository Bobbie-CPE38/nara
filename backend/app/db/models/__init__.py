"""Register ORM tables on Base.metadata for Alembic autogeneration.

Timestamp values must be supplied using app.core.clock.now(), not database defaults.
The remaining model modules will register their referenced tables when merged.
"""

from app.db.models import (  # noqa: F401
    approval_policy,
    approval_request,
    attendance,
    audit_log,
    candidate_item,
    candidate_outreach,
    candidate_plan,
    contact,
    hard_constraint_policy,
    safety_validation,
    soft_constraint_policy,
    staff_working_time_snapshot,
    structured_handover,
)
