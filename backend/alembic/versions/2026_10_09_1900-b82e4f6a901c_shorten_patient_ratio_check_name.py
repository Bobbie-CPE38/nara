"""Shorten the patient-ratio CHECK name without changing its rule.

Revision ID: b82e4f6a901c
Revises: a73d9e2c4b10
"""

from alembic import op

revision = "b82e4f6a901c"
down_revision = "a73d9e2c4b10"
branch_labels = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE hard_constraint_policy RENAME CONSTRAINT "
        "ck_hard_constraint_policy_maximum_patients_per_nurse_po_1310 "
        "TO ck_hard_constraint_policy_patients_per_nurse_valid"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE hard_constraint_policy RENAME CONSTRAINT "
        "ck_hard_constraint_policy_patients_per_nurse_valid "
        "TO ck_hard_constraint_policy_maximum_patients_per_nurse_po_1310"
    )
