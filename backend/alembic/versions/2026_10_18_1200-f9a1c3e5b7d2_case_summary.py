"""Requested case summaries bound to immutable snapshots (round 6 PR S).

Revision ID: f9a1c3e5b7d2
Revises: e7c3a5d9b1f4
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f9a1c3e5b7d2"
down_revision = "e7c3a5d9b1f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_summary",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("case_id", sa.BigInteger(), sa.ForeignKey("staffing_cases.id"), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("input_payload", postgresql.JSONB(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("attempt_limit", sa.Integer(), nullable=False),
        sa.Column("claim", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("case_id", "input_hash", "prompt_version"),
        sa.CheckConstraint(
            "attempts >= 0 AND attempt_limit >= attempts",
            name=op.f("ck_case_summary_attempt_bounds"),
        ),
    )
    op.create_index("ix_case_summary_case_id", "case_summary", ["case_id"])
    op.create_index(
        "ix_case_summary_pending",
        "case_summary",
        ["id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    # Preserve paid usage while removing its subject, just as Demo reset does.
    op.execute(
        "UPDATE llm_call_log SET subject_id = NULL, case_id = NULL, "
        "detached_at = clock_timestamp() WHERE work_type = 'CASE_SUMMARY' AND detached_at IS NULL"
    )
    op.drop_table("case_summary")
