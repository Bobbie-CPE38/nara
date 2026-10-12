"""Add the concurrent-offer policy (round 1 PR 1c).

Revision ID: d91a6c8e203f
Revises: e1f5a8b3c6d2

Offer expiry is added separately in PR O. This migration creates an empty
table; the demo seed supplies policy id=1.
"""

import sqlalchemy as sa
from alembic import op

revision = "d91a6c8e203f"
down_revision = "e1f5a8b3c6d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outreach_policy",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("maximum_concurrent_offers_per_staff", sa.Integer(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "maximum_concurrent_offers_per_staff > 0",
            name=op.f("ck_outreach_policy_offer_limit_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outreach_policy")),
    )


def downgrade() -> None:
    op.drop_table("outreach_policy")
