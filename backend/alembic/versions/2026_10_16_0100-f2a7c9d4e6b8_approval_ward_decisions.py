"""Per-ward decisions and Supervisor waiting period (round 4 PR S).

Revision ID: f2a7c9d4e6b8
Revises: c6e2b9f4a1d7
"""

import sqlalchemy as sa
from alembic import op

revision = "f2a7c9d4e6b8"
down_revision = "c6e2b9f4a1d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing policies normally use 900 seconds. Shorter policies need a valid
    # delay too; refuse a one-second timeout rather than create an invalid policy.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM approval_policy WHERE approval_timeout_seconds <= 1) THEN
            RAISE EXCEPTION 'Supervisor delay requires approval_timeout_seconds > 1';
        END IF;
    END $$""")
    op.add_column("approval_policy", sa.Column("supervisor_after_seconds", sa.Integer()))
    op.execute(
        "UPDATE approval_policy SET supervisor_after_seconds = "
        "LEAST(600, approval_timeout_seconds - 1)"
    )
    op.alter_column("approval_policy", "supervisor_after_seconds", nullable=False)
    op.create_check_constraint(
        op.f("ck_approval_policy_supervisor_delay_valid"),
        "approval_policy",
        "supervisor_after_seconds > 0 AND supervisor_after_seconds < approval_timeout_seconds",
    )
    op.create_table(
        "approval_ward_decision",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "approval_request_id",
            sa.BigInteger(),
            sa.ForeignKey("approval_request.id"),
            nullable=False,
        ),
        sa.Column("ward_id", sa.BigInteger(), sa.ForeignKey("ward.id"), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("approver_id", sa.BigInteger(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("decided_as", sa.Text(), nullable=False),
        sa.Column("is_approved", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("approval_request_id", "side"),
    )


def downgrade() -> None:
    op.drop_table("approval_ward_decision")
    op.drop_constraint(
        op.f("ck_approval_policy_supervisor_delay_valid"), "approval_policy", type_="check"
    )
    op.drop_column("approval_policy", "supervisor_after_seconds")
