"""Roster actual times and explicit transfer links (round 4 PR T2).

Revision ID: b8d4f1a6c2e9
Revises: e1a4c7f2b9d6

Draft parent: rebase onto the staging head after T1 merges before submitting T2.
No backfill: NULL endpoints preserve the existing shift-time fallback.
"""

import sqlalchemy as sa
from alembic import op

revision = "b8d4f1a6c2e9"
down_revision = "e1a4c7f2b9d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("roster_assignment", sa.Column("actual_start_at", sa.DateTime(timezone=True)))
    op.add_column("roster_assignment", sa.Column("actual_end_at", sa.DateTime(timezone=True)))
    op.add_column("roster_assignment", sa.Column("transferred_from_assignment_id", sa.BigInteger()))
    op.create_foreign_key(
        op.f("fk_roster_assignment_transferred_from_assignment_id_roster_assignment"),
        "roster_assignment",
        "roster_assignment",
        ["transferred_from_assignment_id"],
        ["id"],
    )
    op.create_unique_constraint(
        op.f("uq_roster_assignment_transferred_from_assignment_id"),
        "roster_assignment",
        ["transferred_from_assignment_id"],
    )
    op.create_check_constraint(
        op.f("ck_roster_assignment_actual_times_in_order"),
        "roster_assignment",
        "actual_start_at < actual_end_at",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_roster_assignment_actual_times_in_order"), "roster_assignment")
    op.drop_constraint(
        op.f("uq_roster_assignment_transferred_from_assignment_id"),
        "roster_assignment",
        type_="unique",
    )
    op.drop_column("roster_assignment", "transferred_from_assignment_id")
    op.drop_column("roster_assignment", "actual_end_at")
    op.drop_column("roster_assignment", "actual_start_at")
