"""Solver time limit policy column (round 2 PR B).

Revision ID: c9e4a7b2d5f8
Revises: b7d2f8a1c6e4

Existing policy rows get a 3 second limit.
"""

import sqlalchemy as sa
from alembic import op

revision = "c9e4a7b2d5f8"
down_revision = "b7d2f8a1c6e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "soft_constraint_policy",
        sa.Column("solver_time_limit_seconds", sa.Integer(), nullable=False, server_default="3"),
    )
    op.alter_column("soft_constraint_policy", "solver_time_limit_seconds", server_default=None)
    op.create_check_constraint(
        op.f("ck_soft_constraint_policy_solver_time_limit_positive"),
        "soft_constraint_policy",
        "solver_time_limit_seconds > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_soft_constraint_policy_solver_time_limit_positive"),
        "soft_constraint_policy",
        type_="check",
    )
    op.drop_column("soft_constraint_policy", "solver_time_limit_seconds")
