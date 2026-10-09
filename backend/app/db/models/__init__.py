# Import every model module here so its tables register on Base.metadata
# (alembic/env.py imports this package for autogenerate)
from app.db.models import (  # noqa: F401
    approval_policy,
    candidate_item,
    candidate_plan,
    hard_constraint_policy,
    safety_validation,
    soft_constraint_policy,
    staff_working_time_snapshot,
)
