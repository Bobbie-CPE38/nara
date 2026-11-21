"""Outreach limits of a case: at most N waves, and no new wave after a deadline (round 6 PR EV6).

Revision ID: c3e5a7b9d1f2
Revises: f2c9a1d6e8b4

docs/workflow.md 6.36.8. Existing policies adopt 10 waves and 90 minutes from the opening of
the case. New policies must supply both explicitly (no permanent server default), like
offer_timeout_seconds.
"""

import sqlalchemy as sa
from alembic import op

revision = "c3e5a7b9d1f2"
down_revision = "f2c9a1d6e8b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outreach_policy",
        sa.Column("maximum_waves_per_case", sa.Integer(), nullable=False, server_default="10"),
    )
    op.add_column(
        "outreach_policy",
        sa.Column(
            "case_outreach_deadline_seconds", sa.Integer(), nullable=False, server_default="5400"
        ),
    )
    op.alter_column("outreach_policy", "maximum_waves_per_case", server_default=None)
    op.alter_column("outreach_policy", "case_outreach_deadline_seconds", server_default=None)
    op.create_check_constraint(
        op.f("ck_outreach_policy_wave_limit_positive"),
        "outreach_policy",
        "maximum_waves_per_case > 0",
    )
    op.create_check_constraint(
        op.f("ck_outreach_policy_case_deadline_positive"),
        "outreach_policy",
        "case_outreach_deadline_seconds > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_outreach_policy_case_deadline_positive"), "outreach_policy", type_="check"
    )
    op.drop_constraint(
        op.f("ck_outreach_policy_wave_limit_positive"), "outreach_policy", type_="check"
    )
    op.drop_column("outreach_policy", "case_outreach_deadline_seconds")
    op.drop_column("outreach_policy", "maximum_waves_per_case")
