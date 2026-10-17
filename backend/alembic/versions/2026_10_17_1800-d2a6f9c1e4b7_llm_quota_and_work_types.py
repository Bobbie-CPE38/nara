"""LLM call log for every work type, and the DEMO and TRIAL quota counters (round 6 PR B1).

Revision ID: d2a6f9c1e4b7
Revises: c5f8b0d3e7a1
"""

import sqlalchemy as sa
from alembic import op

revision = "d2a6f9c1e4b7"
down_revision = "c5f8b0d3e7a1"
branch_labels = None
depends_on = None

# Copied, not imported: a migration must not change when the model does
WORK_TYPE_SUBJECT_CHECK = (
    "(work_type = 'RANK_EXPLANATION' AND explanation_id IS NOT NULL AND case_id IS NOT NULL"
    " AND plan_id IS NOT NULL AND subject_id IS NULL AND trial_run_id IS NULL"
    " AND trial_case_key IS NULL)"
    " OR (work_type = 'CASE_SUMMARY' AND subject_id IS NOT NULL AND case_id IS NOT NULL"
    " AND explanation_id IS NULL AND plan_id IS NULL AND trial_run_id IS NULL"
    " AND trial_case_key IS NULL)"
    " OR (work_type = 'MODEL_TRIAL' AND trial_run_id IS NOT NULL AND trial_case_key IS NOT NULL"
    " AND explanation_id IS NULL AND case_id IS NULL AND plan_id IS NULL"
    " AND subject_id IS NULL)"
)


def upgrade() -> None:
    # Every existing row is a ranking explanation; new rows must name their type
    op.add_column(
        "llm_call_log",
        sa.Column("work_type", sa.Text(), nullable=False, server_default="RANK_EXPLANATION"),
    )
    op.alter_column("llm_call_log", "work_type", server_default=None)
    op.add_column("llm_call_log", sa.Column("subject_id", sa.BigInteger()))
    op.add_column("llm_call_log", sa.Column("trial_run_id", sa.Text()))
    op.add_column("llm_call_log", sa.Column("trial_case_key", sa.Text()))
    for column in ("explanation_id", "case_id", "plan_id"):
        op.alter_column("llm_call_log", column, existing_type=sa.BigInteger(), nullable=True)
    op.create_check_constraint(
        op.f("ck_llm_call_log_work_type_subject"), "llm_call_log", WORK_TYPE_SUBJECT_CHECK
    )
    op.create_index(
        "uq_llm_call_log_case_summary_attempt",
        "llm_call_log",
        ["subject_id", "attempt"],
        unique=True,
        postgresql_where=sa.text("work_type = 'CASE_SUMMARY'"),
    )
    op.create_index(
        "uq_llm_call_log_model_trial_attempt",
        "llm_call_log",
        ["trial_run_id", "trial_case_key", "attempt"],
        unique=True,
        postgresql_where=sa.text("work_type = 'MODEL_TRIAL'"),
    )
    op.create_table(
        "llm_daily_usage",
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.CheckConstraint("used >= 0", name=op.f("ck_llm_daily_usage_used_not_negative")),
        sa.PrimaryKeyConstraint("usage_date", name=op.f("pk_llm_daily_usage")),
    )
    op.create_table(
        "llm_trial_usage",
        sa.Column("trial_run_id", sa.Text(), nullable=False),
        sa.Column("cap", sa.Integer(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cap >= 0", name=op.f("ck_llm_trial_usage_cap_not_negative")),
        sa.CheckConstraint(
            "used >= 0 AND used <= cap", name=op.f("ck_llm_trial_usage_used_within_cap")
        ),
        sa.PrimaryKeyConstraint("trial_run_id", name=op.f("pk_llm_trial_usage")),
    )


def downgrade() -> None:
    op.drop_table("llm_trial_usage")
    op.drop_table("llm_daily_usage")
    # Case summary and trial attempts cannot fit the old explanation-only schema. Their
    # cost history is lost with them
    op.execute("DELETE FROM llm_call_log WHERE work_type <> 'RANK_EXPLANATION'")
    op.drop_index("uq_llm_call_log_model_trial_attempt", table_name="llm_call_log")
    op.drop_index("uq_llm_call_log_case_summary_attempt", table_name="llm_call_log")
    op.drop_constraint(op.f("ck_llm_call_log_work_type_subject"), "llm_call_log", type_="check")
    for column in ("explanation_id", "case_id", "plan_id"):
        op.alter_column("llm_call_log", column, existing_type=sa.BigInteger(), nullable=False)
    op.drop_column("llm_call_log", "trial_case_key")
    op.drop_column("llm_call_log", "trial_run_id")
    op.drop_column("llm_call_log", "subject_id")
    op.drop_column("llm_call_log", "work_type")
