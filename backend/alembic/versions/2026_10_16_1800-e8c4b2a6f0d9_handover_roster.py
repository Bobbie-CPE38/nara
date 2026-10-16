"""Bind each handover to one replacement roster row (round 5 H1).

Revision ID: e8c4b2a6f0d9
Revises: a4d8e1b7c3f5
"""

import sqlalchemy as sa
from alembic import op

revision = "e8c4b2a6f0d9"
down_revision = "a4d8e1b7c3f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No producer existed before H1. NOT NULL deliberately refuses unexpected
    # legacy handovers instead of guessing which roster row they belong to.
    op.add_column(
        "structured_handover",
        sa.Column("roster_assignment_id", sa.BigInteger(), nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_structured_handover_roster_assignment_id_roster_assignment"),
        "structured_handover",
        "roster_assignment",
        ["roster_assignment_id"],
        ["id"],
    )
    op.create_unique_constraint(
        op.f("uq_structured_handover_roster_assignment_id"),
        "structured_handover",
        ["roster_assignment_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_structured_handover_roster_assignment_id"), "structured_handover", type_="unique"
    )
    op.drop_constraint(
        op.f("fk_structured_handover_roster_assignment_id_roster_assignment"),
        "structured_handover",
        type_="foreignkey",
    )
    op.drop_column("structured_handover", "roster_assignment_id")
