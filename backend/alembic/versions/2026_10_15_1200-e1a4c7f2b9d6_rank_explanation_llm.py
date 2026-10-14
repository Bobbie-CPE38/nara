"""LLM ranking explanation and per-attempt call log (round 3 PR X).

Revision ID: e1a4c7f2b9d6
Revises: d7f0b3c5e9a2
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e1a4c7f2b9d6"
down_revision = "d7f0b3c5e9a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rank_explanation",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text()),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("text", sa.Text()),
        sa.Column("provider", sa.Text()),
        sa.Column("model_id", sa.Text()),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("claim", postgresql.UUID(as_uuid=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["staffing_cases.id"],
            name=op.f("fk_rank_explanation_case_id_staffing_cases"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["candidate_plans.id"],
            name=op.f("fk_rank_explanation_plan_id_candidate_plans"),
        ),
        sa.UniqueConstraint("plan_id", "prompt_version", name=op.f("uq_rank_explanation_plan_id")),
    )
    op.create_index(
        "ix_rank_explanation_pending",
        "rank_explanation",
        ["id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_table(
        "llm_call_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("explanation_id", sa.BigInteger(), nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text()),
        sa.Column("region", sa.Text()),
        sa.Column("input_hash", sa.Text()),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_type", sa.Text()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("input_price_per_mtok_usd", sa.Numeric(12, 6)),
        sa.Column("output_price_per_mtok_usd", sa.Numeric(12, 6)),
        sa.Column("estimated_cost_usd", sa.Numeric(14, 8)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["explanation_id"],
            ["rank_explanation.id"],
            name=op.f("fk_llm_call_log_explanation_id_rank_explanation"),
        ),
        sa.UniqueConstraint(
            "explanation_id", "attempt", name=op.f("uq_llm_call_log_explanation_id")
        ),
    )
    op.create_index("ix_llm_call_log_plan_id", "llm_call_log", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_call_log_plan_id", table_name="llm_call_log")
    op.drop_table("llm_call_log")
    op.drop_index("ix_rank_explanation_pending", table_name="rank_explanation")
    op.drop_table("rank_explanation")
