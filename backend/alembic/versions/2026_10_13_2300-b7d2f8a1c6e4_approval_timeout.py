"""Approval deadlines and offer-specific attempts (round 2 PR T).

Revision ID: b7d2f8a1c6e4
Revises: a4b8c2d6e9f1

All policies are initialized to 900 seconds by this migration, so historical
deadlines use requested_at + 900 seconds, including decided and inactive rows.
Old actionable requests expire on the first job tick after deployment.

Downgrade removes attempt identity. After a retry creates two offers for an
item, re-upgrade deliberately refuses that ambiguous history; repair it before
re-upgrading rather than selecting an offer arbitrarily.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7d2f8a1c6e4"
down_revision = "a4b8c2d6e9f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fail before DDL rather than guessing an offer for historical records.
    op.execute("""DO $$ BEGIN
        IF EXISTS (
            SELECT 1 FROM (
                SELECT case_id, candidate_item_id FROM approval_request
                UNION SELECT case_id, candidate_item_id FROM safety_validation
            ) h LEFT JOIN candidate_outreach o
              ON o.case_id = h.case_id AND o.candidate_item_id = h.candidate_item_id
            GROUP BY h.case_id, h.candidate_item_id HAVING COUNT(o.id) != 1
        ) THEN
            RAISE EXCEPTION 'Cannot link approval/Safety history: %',
                'expected exactly one offer per case/item; repair missing or duplicate offers';
        END IF;
    END $$""")
    op.add_column(
        "approval_policy",
        sa.Column("approval_timeout_seconds", sa.Integer(), nullable=False, server_default="900"),
    )
    op.alter_column("approval_policy", "approval_timeout_seconds", server_default=None)
    op.create_check_constraint(
        op.f("ck_approval_policy_approval_timeout_positive"),
        "approval_policy",
        "approval_timeout_seconds > 0",
    )
    op.add_column("approval_request", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "approval_request",
        sa.Column("is_timed_out", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE approval_request SET expires_at = requested_at + INTERVAL '900 seconds'")
    op.alter_column("approval_request", "expires_at", nullable=False)
    for table in ("approval_request", "safety_validation"):
        op.add_column(table, sa.Column("outreach_id", sa.BigInteger()))
        op.execute(f"""UPDATE {table} h SET outreach_id = o.id FROM candidate_outreach o
            WHERE h.case_id = o.case_id AND h.candidate_item_id = o.candidate_item_id""")
        op.alter_column(table, "outreach_id", nullable=False)
        op.create_foreign_key(
            op.f(f"fk_{table}_outreach_id_candidate_outreach"),
            table,
            "candidate_outreach",
            ["outreach_id"],
            ["id"],
        )
    op.create_index(
        "ix_approval_request_pending_expiry",
        "approval_request",
        ["expires_at"],
        postgresql_where=sa.text("is_pending = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_approval_request_pending_expiry", table_name="approval_request")
    for table in ("safety_validation", "approval_request"):
        op.drop_constraint(
            op.f(f"fk_{table}_outreach_id_candidate_outreach"), table, type_="foreignkey"
        )
        op.drop_column(table, "outreach_id")
    op.drop_column("approval_request", "is_timed_out")
    op.drop_column("approval_request", "expires_at")
    op.drop_constraint(
        op.f("ck_approval_policy_approval_timeout_positive"), "approval_policy", type_="check"
    )
    op.drop_column("approval_policy", "approval_timeout_seconds")
