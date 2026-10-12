"""Add the consecutive-shift limit to hard policy and the overtime CHECK to attendance.

Revision ID: e1f5a8b3c6d2
Revises: c4d7e19a52f3

Round 1 contract, section 7.2. Existing policies are backfilled with 7, the
limit the team agreed on. The temporary default is removed so new policy
versions must supply their own limit.

The attendance CHECK passes while overtime_minutes or work_minutes is NULL:
NULL means the row is not summarised yet, not 0.
"""

import sqlalchemy as sa
from alembic import op

revision = "e1f5a8b3c6d2"
down_revision = "c4d7e19a52f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hard_constraint_policy",
        sa.Column("maximum_consecutive_shifts", sa.Integer(), nullable=False, server_default="7"),
    )
    op.alter_column("hard_constraint_policy", "maximum_consecutive_shifts", server_default=None)
    op.create_check_constraint(
        op.f("ck_hard_constraint_policy_consecutive_shifts_non_negative"),
        "hard_constraint_policy",
        "maximum_consecutive_shifts >= 0",
    )
    op.create_check_constraint(
        op.f("ck_attendance_overtime_within_work"),
        "attendance",
        "overtime_minutes >= 0 AND overtime_minutes <= work_minutes",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_attendance_overtime_within_work"), "attendance", type_="check")
    op.drop_constraint(
        op.f("ck_hard_constraint_policy_consecutive_shifts_non_negative"),
        "hard_constraint_policy",
        type_="check",
    )
    op.drop_column("hard_constraint_policy", "maximum_consecutive_shifts")
