"""Final offer outcomes and their separate LINE outbox; no historical backfill."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b4e7a9c2d6f0"
down_revision = "f6b2d8a4c0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_outcome_notification",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "outreach_id", sa.BigInteger(), sa.ForeignKey("candidate_outreach.id"), nullable=False
        ),
        sa.Column("case_id", sa.BigInteger(), sa.ForeignKey("staffing_cases.id"), nullable=False),
        sa.Column("staff_id", sa.BigInteger(), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("audit_id", sa.BigInteger(), sa.ForeignKey("audit_log.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_status", sa.Text()),
        sa.Column("delivery_payload", postgresql.JSONB()),
        sa.Column("delivery_retry_key", sa.Text()),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivery_next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("delivery_lease_until", sa.DateTime(timezone=True)),
        sa.Column("delivery_claim", sa.Text()),
        sa.Column("delivery_last_result", sa.Text()),
        sa.UniqueConstraint("outreach_id", name=op.f("uq_offer_outcome_notification_outreach_id")),
        sa.CheckConstraint(
            "delivery_attempts BETWEEN 0 AND 3",
            name=op.f("ck_offer_outcome_notification_delivery_attempts"),
        ),
        sa.CheckConstraint(
            "delivery_status IS NULL OR delivery_status IN "
            "('PENDING','ACCEPTED','FAILED','CANCELLED','NO_CONTACT')",
            name=op.f("ck_offer_outcome_notification_delivery_status"),
        ),
    )
    op.create_index(
        "ix_offer_outcome_notification_delivery_due",
        "offer_outcome_notification",
        ["delivery_next_attempt_at"],
        postgresql_where=sa.text("delivery_status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_table("offer_outcome_notification")
