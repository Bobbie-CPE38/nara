"""Add the workload snapshot (patient count and ratio) to staffing gap.

Revision ID: c4d7e19a52f3
Revises: b82e4f6a901c

No backfill: filling old rows with today's SHIFT and policy values would make
them look like snapshots of the past. No gap row exists before this revision
(assess_staffing was still a stub), so the upgrade stops if it finds one.

The check runs inside the database, not in Python: `alembic upgrade --sql` has
no connection and no query result, so the generated script must carry the
check itself. It is the first statement, and DDL is transactional, so a refusal
leaves the schema untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d7e19a52f3"
down_revision = "b82e4f6a901c"
branch_labels = None
depends_on = None

EXISTING_ROWS_MESSAGE = (
    "staffing_gap already has rows, and their patient_count and patients_per_nurse "
    "cannot be known. Run make reset to empty the database, then upgrade again."
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
    op.add_column("staffing_gap", sa.Column("patient_count", sa.Integer(), nullable=False))
    op.add_column("staffing_gap", sa.Column("patients_per_nurse", sa.Numeric(), nullable=False))
    op.create_check_constraint(
        op.f("ck_staffing_gap_patients_per_nurse_valid"),
        "staffing_gap",
        "patients_per_nurse > 0 AND patients_per_nurse < 'Infinity'::numeric",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_staffing_gap_patients_per_nurse_valid"), "staffing_gap", type_="check"
    )
    op.drop_column("staffing_gap", "patients_per_nurse")
    op.drop_column("staffing_gap", "patient_count")
