"""Attendance belongs to a shift (round 5 PR N1).

Revision ID: a4d8e1b7c3f5
Revises: f2a7c9d4e6b8
"""

import sqlalchemy as sa
from alembic import op

revision = "a4d8e1b7c3f5"
down_revision = "f2a7c9d4e6b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows stay without a shift; no backfill
    op.add_column(
        "attendance",
        sa.Column(
            "shift_id",
            sa.BigInteger(),
            sa.ForeignKey("shift.id", name=op.f("fk_attendance_shift_id_shift")),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_attendance_staff_shift",
        "attendance",
        ["staff_id", "shift_id"],
        unique=True,
        postgresql_where=sa.text("shift_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_attendance_staff_shift", table_name="attendance")
    op.drop_column("attendance", "shift_id")
