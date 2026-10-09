"""Add the hospital-wide patients-per-nurse limit to hard policy.

Revision ID: a73d9e2c4b10
Revises: 63c7709cfe6c

Existing skeleton policies are backfilled with the demo value 2. The temporary
default is removed so new policy versions must explicitly supply their ratio.
"""

import sqlalchemy as sa
from alembic import op

revision = "a73d9e2c4b10"
down_revision = "63c7709cfe6c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hard_constraint_policy",
        sa.Column("maximum_patients_per_nurse", sa.Numeric(), nullable=False, server_default="2"),
    )
    op.alter_column("hard_constraint_policy", "maximum_patients_per_nurse", server_default=None)
    op.create_check_constraint(
        op.f("ck_hard_constraint_policy_maximum_patients_per_nurse_positive_finite"),
        "hard_constraint_policy",
        "maximum_patients_per_nurse > 0 AND maximum_patients_per_nurse < 'Infinity'::numeric",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_hard_constraint_policy_maximum_patients_per_nurse_positive_finite"),
        "hard_constraint_policy",
        type_="check",
    )
    op.drop_column("hard_constraint_policy", "maximum_patients_per_nurse")
