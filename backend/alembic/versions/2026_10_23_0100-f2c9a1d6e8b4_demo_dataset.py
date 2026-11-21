"""Opt-in repeatable large demo profile.

Revision ID: f2c9a1d6e8b4
Revises: b8f3d5a0c2e4
"""

import sqlalchemy as sa
from alembic import op

revision = "f2c9a1d6e8b4"
down_revision = "b8f3d5a0c2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_dataset",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("profile", sa.Text(), unique=True, nullable=False),
        sa.Column("reference_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("demo_dataset")
