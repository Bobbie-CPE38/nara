"""Auto-approval per ward side and a Supervisor queue (round 6 PR EV9).

Revision ID: e7b9d1f3a5c8
Revises: c3e5a7b9d1f2

docs/workflow.md 6.39. APPROVAL_POLICY gains the Supervisor queue's own capacity
(`supervisor_ratio` x active Supervisors, at most `supervisor_incoming_count`); existing
policies adopt 5 and 10, and new policies must supply both explicitly (no permanent server
default). APPROVAL_WARD_DECISION also records sides the system decided: `approval_mode` is
AUTO, `approver_id` is empty, and the queue, its cap and the approvers counted that made the
side eligible are kept to explain the decision later. Every existing row is a person's.
"""

import sqlalchemy as sa
from alembic import op

revision = "e7b9d1f3a5c8"
down_revision = "c3e5a7b9d1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "approval_policy",
        sa.Column("supervisor_ratio", sa.Numeric(), nullable=False, server_default="5"),
    )
    op.add_column(
        "approval_policy",
        sa.Column("supervisor_incoming_count", sa.Integer(), nullable=False, server_default="10"),
    )
    op.alter_column("approval_policy", "supervisor_ratio", server_default=None)
    op.alter_column("approval_policy", "supervisor_incoming_count", server_default=None)
    op.create_check_constraint(
        op.f("ck_approval_policy_supervisor_capacity_valid"),
        "approval_policy",
        "supervisor_ratio >= 0 AND supervisor_incoming_count >= 0",
    )

    op.add_column(
        "approval_ward_decision",
        sa.Column("approval_mode", sa.Text(), nullable=False, server_default="MANUAL"),
    )
    op.alter_column("approval_ward_decision", "approval_mode", server_default=None)
    op.add_column("approval_ward_decision", sa.Column("queue_count", sa.Integer()))
    op.add_column("approval_ward_decision", sa.Column("queue_cap", sa.Numeric()))
    op.add_column("approval_ward_decision", sa.Column("queue_approver_count", sa.Integer()))
    op.alter_column("approval_ward_decision", "approver_id", nullable=True)
    op.create_check_constraint(
        op.f("ck_approval_ward_decision_mode_matches_decider"),
        "approval_ward_decision",
        "(approval_mode = 'MANUAL' AND approver_id IS NOT NULL AND queue_count IS NULL"
        " AND queue_cap IS NULL AND queue_approver_count IS NULL)"
        " OR (approval_mode = 'AUTO' AND approver_id IS NULL AND is_approved"
        " AND queue_count IS NOT NULL AND queue_cap IS NOT NULL"
        " AND queue_approver_count IS NOT NULL AND queue_count > queue_cap)",
    )


def downgrade() -> None:
    # A side the system decided has no person to keep: refuse rather than invent one
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM approval_ward_decision WHERE approval_mode = 'AUTO') THEN
            RAISE EXCEPTION 'Automatic ward decisions exist; downgrade would lose them';
        END IF;
    END $$""")
    op.drop_constraint(
        op.f("ck_approval_ward_decision_mode_matches_decider"),
        "approval_ward_decision",
        type_="check",
    )
    op.alter_column("approval_ward_decision", "approver_id", nullable=False)
    op.drop_column("approval_ward_decision", "queue_approver_count")
    op.drop_column("approval_ward_decision", "queue_cap")
    op.drop_column("approval_ward_decision", "queue_count")
    op.drop_column("approval_ward_decision", "approval_mode")
    op.drop_constraint(
        op.f("ck_approval_policy_supervisor_capacity_valid"), "approval_policy", type_="check"
    )
    op.drop_column("approval_policy", "supervisor_incoming_count")
    op.drop_column("approval_policy", "supervisor_ratio")
