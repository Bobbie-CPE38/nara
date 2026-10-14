"""Add manual_assignment: roster rows a head nurse created for a case (round 2 PR H).

Revision ID: b7d3e5a1c9f2
Revises: c9e4a7b2d5f8

Third and last migration of round 2, after T (b7d2f8a1c6e4) and B (c9e4a7b2d5f8).
"""

import sqlalchemy as sa
from alembic import op

revision = "b7d3e5a1c9f2"
down_revision = "c9e4a7b2d5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_assignment",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("roster_assignment_id", sa.BigInteger(), nullable=False),
        sa.Column("assigned_by", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["staffing_cases.id"],
            name=op.f("fk_manual_assignment_case_id_staffing_cases"),
        ),
        sa.ForeignKeyConstraint(
            ["roster_assignment_id"],
            ["roster_assignment.id"],
            name=op.f("fk_manual_assignment_roster_assignment_id_roster_assignment"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by"], ["staff.id"], name=op.f("fk_manual_assignment_assigned_by_staff")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manual_assignment")),
        sa.UniqueConstraint(
            "roster_assignment_id", name=op.f("uq_manual_assignment_roster_assignment_id")
        ),
    )
    op.create_index(
        op.f("ix_manual_assignment_case_id"), "manual_assignment", ["case_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_manual_assignment_case_id"), table_name="manual_assignment")
    op.drop_table("manual_assignment")
