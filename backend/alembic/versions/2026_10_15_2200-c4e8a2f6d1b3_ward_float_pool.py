"""Mark the Float Pool ward (round 4 PR C1).

Revision ID: c4e8a2f6d1b3
Revises: b8d4f1a6c2e9

docs/workflow.md section 6.19: staff whose home ward is_float_pool are candidates
with source FLOAT_POOL. No backfill: existing wards become non-float (default false).
"""

import sqlalchemy as sa
from alembic import op

revision = "c4e8a2f6d1b3"
down_revision = "b8d4f1a6c2e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ward",
        sa.Column("is_float_pool", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("ward", "is_float_pool")
