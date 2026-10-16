"""Durable Handover LINE intents; existing snapshots remain unsent."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f6b2d8a4c0e1"
down_revision = "e8c4b2a6f0d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("delivery_status", "delivery_retry_key", "delivery_claim", "delivery_last_result"):
        op.add_column("structured_handover", sa.Column(name, sa.Text(), nullable=True))
    op.add_column(
        "structured_handover", sa.Column("delivery_payload", postgresql.JSONB(), nullable=True)
    )
    for name in ("delivery_next_attempt_at", "delivery_lease_until"):
        op.add_column(
            "structured_handover", sa.Column(name, sa.DateTime(timezone=True), nullable=True)
        )
    op.add_column(
        "structured_handover",
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        op.f("ck_structured_handover_delivery_attempts"),
        "structured_handover",
        "delivery_attempts >= 0 AND delivery_attempts <= 3",
    )
    op.create_check_constraint(
        op.f("ck_structured_handover_delivery_status"),
        "structured_handover",
        "delivery_status IS NULL OR "
        "delivery_status IN ('PENDING','ACCEPTED','FAILED','CANCELLED','NO_CONTACT')",
    )
    op.create_index(
        "ix_structured_handover_delivery_due",
        "structured_handover",
        ["delivery_next_attempt_at"],
        postgresql_where=sa.text("delivery_status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index("ix_structured_handover_delivery_due", table_name="structured_handover")
    op.drop_constraint(
        op.f("ck_structured_handover_delivery_status"), "structured_handover", type_="check"
    )
    op.drop_constraint(
        op.f("ck_structured_handover_delivery_attempts"), "structured_handover", type_="check"
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
        op.drop_column("structured_handover", name)
