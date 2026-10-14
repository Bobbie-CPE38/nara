"""Durable LINE delivery and webhook event deduplication (round 3 PR L).

Revision ID: c6e9a2b4d8f1
Revises: b7d3e5a1c9f2

Historical/simulator offers have no delivery intent; never send them on upgrade.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c6e9a2b4d8f1"
down_revision = "b7d3e5a1c9f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "line_webhook_event",
        sa.Column("webhook_event_id", sa.Text(), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name in ("delivery_status", "delivery_retry_key", "delivery_claim", "delivery_last_result"):
        op.add_column("candidate_outreach", sa.Column(name, sa.Text(), nullable=True))
    op.add_column(
        "candidate_outreach", sa.Column("delivery_payload", postgresql.JSONB(), nullable=True)
    )
    for name in ("delivery_next_attempt_at", "delivery_lease_until"):
        op.add_column(
            "candidate_outreach", sa.Column(name, sa.DateTime(timezone=True), nullable=True)
        )
    op.add_column(
        "candidate_outreach",
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        op.f("ck_candidate_outreach_delivery_attempts"),
        "candidate_outreach",
        "delivery_attempts >= 0 AND delivery_attempts <= 3",
    )
    op.create_check_constraint(
        op.f("ck_candidate_outreach_delivery_status"),
        "candidate_outreach",
        "delivery_status IS NULL OR "
        "delivery_status IN ('PENDING','ACCEPTED','FAILED','CANCELLED','NO_CONTACT')",
    )
    op.create_index(
        "ix_candidate_outreach_delivery_due",
        "candidate_outreach",
        ["delivery_next_attempt_at"],
        postgresql_where=sa.text("delivery_status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_outreach_delivery_due", table_name="candidate_outreach")
    op.drop_constraint(
        op.f("ck_candidate_outreach_delivery_status"), "candidate_outreach", type_="check"
    )
    op.drop_constraint(
        op.f("ck_candidate_outreach_delivery_attempts"), "candidate_outreach", type_="check"
    )
    for name in (
        "delivery_status",
        "delivery_retry_key",
        "delivery_claim",
        "delivery_last_result",
        "delivery_payload",
        "delivery_next_attempt_at",
        "delivery_lease_until",
        "delivery_attempts",
    ):
        op.drop_column("candidate_outreach", name)
    op.drop_table("line_webhook_event")
