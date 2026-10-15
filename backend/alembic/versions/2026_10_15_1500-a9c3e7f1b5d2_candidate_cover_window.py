"""Add the cover window and source assignment to candidate items (round 4 PR T1).

Revision ID: a9c3e7f1b5d2
Revises: e1a4c7f2b9d6

Round 4 contract, section 6.20.
  * candidate_items.cover_start_at / cover_end_at: the part of the shift the candidate
    covers. Both NULL means the whole shift, so every existing row keeps its meaning.
  * candidate_items.source_assignment_id: the roster row the candidate is moved out of.
    NULL means the candidate is not being moved.
"""

import sqlalchemy as sa
from alembic import op

revision = "a9c3e7f1b5d2"
down_revision = "e1a4c7f2b9d6"
branch_labels = None
depends_on = None

SOURCE_FK = "fk_candidate_items_source_assignment_id_roster_assignment"
BOTH_OR_NEITHER = "ck_candidate_items_cover_both_or_neither"
IN_ORDER = "ck_candidate_items_cover_in_order"


def upgrade() -> None:
    op.add_column(
        "candidate_items", sa.Column("cover_start_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "candidate_items", sa.Column("cover_end_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "candidate_items", sa.Column("source_assignment_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        op.f(SOURCE_FK),
        "candidate_items",
        "roster_assignment",
        ["source_assignment_id"],
        ["id"],
    )
    op.create_check_constraint(
        op.f(BOTH_OR_NEITHER),
        "candidate_items",
        "(cover_start_at IS NULL) = (cover_end_at IS NULL)",
    )
    op.create_check_constraint(op.f(IN_ORDER), "candidate_items", "cover_start_at < cover_end_at")


def downgrade() -> None:
    op.drop_constraint(op.f(IN_ORDER), "candidate_items", type_="check")
    op.drop_constraint(op.f(BOTH_OR_NEITHER), "candidate_items", type_="check")
    # Dropping the column also drops its foreign key
    op.drop_column("candidate_items", "source_assignment_id")
    op.drop_column("candidate_items", "cover_end_at")
    op.drop_column("candidate_items", "cover_start_at")
