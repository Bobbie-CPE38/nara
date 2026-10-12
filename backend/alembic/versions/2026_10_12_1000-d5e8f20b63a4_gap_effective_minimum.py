"""Replace the workload snapshot on staffing gap with effective_minimum.

Revision ID: d5e8f20b63a4
Revises: c4d7e19a52f3

The gap is now measured against required_staff and minimum_staff of the
requirement, so the row stores the target it used (effective_minimum) instead
of patient_count and patients_per_nurse.

No backfill in either direction: the target of an old row cannot be rebuilt
from today's requirement, which is updated in place. The upgrade and the
downgrade stop if staffing_gap has rows. The check runs inside the database so
that `alembic upgrade --sql` carries it too (see c4d7e19a52f3).
"""

import sqlalchemy as sa
from alembic import op

revision = "d5e8f20b63a4"
down_revision = "c4d7e19a52f3"
branch_labels = None
depends_on = None

EXISTING_ROWS_MESSAGE = (
    "staffing_gap already has rows, and their effective_minimum cannot be known. "
    "Run make reset to empty the database, then migrate again."
)
REFUSE_EXISTING_ROWS = f"""
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM staffing_gap) THEN
        RAISE EXCEPTION '{EXISTING_ROWS_MESSAGE}';
    END IF;
END
$$
"""


def upgrade() -> None:
    op.execute(REFUSE_EXISTING_ROWS)
    op.drop_constraint(
        op.f("ck_staffing_gap_patients_per_nurse_valid"), "staffing_gap", type_="check"
    )
    op.drop_column("staffing_gap", "patients_per_nurse")
    op.drop_column("staffing_gap", "patient_count")
    op.add_column("staffing_gap", sa.Column("effective_minimum", sa.Integer(), nullable=False))


def downgrade() -> None:
    op.execute(REFUSE_EXISTING_ROWS)
    op.drop_column("staffing_gap", "effective_minimum")
    op.add_column("staffing_gap", sa.Column("patient_count", sa.Integer(), nullable=False))
    op.add_column("staffing_gap", sa.Column("patients_per_nurse", sa.Numeric(), nullable=False))
    op.create_check_constraint(
        op.f("ck_staffing_gap_patients_per_nurse_valid"),
        "staffing_gap",
        "patients_per_nurse > 0 AND patients_per_nurse < 'Infinity'::numeric",
    )
