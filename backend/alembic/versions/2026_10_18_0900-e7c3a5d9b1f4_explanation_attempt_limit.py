"""Ranking explanations made only when a user asks (round 6 PR E1).

attempt_limit is how many attempts the row may have reached when the current request ends.
NULL means no user asked: the row was queued by the workflow before E1, and the sweep
leaves it alone until someone asks (docs/workflow.md 6.27).

Revision ID: e7c3a5d9b1f4
Revises: d2a6f9c1e4b7
"""

import sqlalchemy as sa
from alembic import op

revision = "e7c3a5d9b1f4"
down_revision = "d2a6f9c1e4b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rank_explanation", sa.Column("attempt_limit", sa.Integer()))


def downgrade() -> None:
    # The old sweep takes every PENDING row. Untried rows nobody asked for go, so a
    # downgrade does not start calls on its own (a tried row has log rows pointing at it)
    op.execute(
        "DELETE FROM rank_explanation"
        " WHERE status = 'PENDING' AND attempt_limit IS NULL AND attempts = 0"
    )
    op.drop_column("rank_explanation", "attempt_limit")
