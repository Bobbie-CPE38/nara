"""Columns of the merge window (round 1 PR M).

Revision ID: f2a6b9c4d7e1
Revises: d91a6c8e203f

Events of one shift wait in a window and open one case together, so a case can
have several events. The link moves from staffing_cases.event_id to
staffing_events.case_id, and an audit row about an event carries event_id.

No backfill in either direction (docs/workflow.md section 3.2, Q34): the window
length of an existing shift is not known, and neither direction moves the link
between events and cases. The upgrade stops if shift, staffing_events or
staffing_cases has rows; the downgrade stops if staffing_cases has rows. The
check runs inside the database so that `alembic upgrade --sql` carries it too
(see c4d7e19a52f3).
"""

import sqlalchemy as sa
from alembic import op

revision = "f2a6b9c4d7e1"
down_revision = "d91a6c8e203f"
branch_labels = None
depends_on = None

EXISTING_ROWS_MESSAGE = (
    "shift, staffing_events or staffing_cases already has rows, and this migration "
    "does not fill merge_window_seconds or move the link between events and cases. "
    "Run make reset to empty the database, then migrate again."
)
DOWNGRADE_EXISTING_ROWS_MESSAGE = (
    "staffing_cases already has rows, and their event_id is not filled by this "
    "downgrade. Run make reset to empty the database, then migrate again."
)


def _refuse_existing_rows(tables: tuple[str, ...], message: str) -> str:
    exists = " OR ".join(f"EXISTS (SELECT 1 FROM {table})" for table in tables)
    return f"""
DO $$
BEGIN
    IF {exists} THEN
        RAISE EXCEPTION '{message}';
    END IF;
END
$$
"""


REFUSE_EXISTING_ROWS = _refuse_existing_rows(
    ("shift", "staffing_events", "staffing_cases"), EXISTING_ROWS_MESSAGE
)
REFUSE_EXISTING_ROWS_ON_DOWNGRADE = _refuse_existing_rows(
    ("staffing_cases",), DOWNGRADE_EXISTING_ROWS_MESSAGE
)


def upgrade() -> None:
    op.execute(REFUSE_EXISTING_ROWS)
    op.add_column("shift", sa.Column("merge_window_seconds", sa.Integer(), nullable=False))
    op.create_check_constraint(
        op.f("ck_shift_merge_window_seconds_non_negative"),
        "shift",
        "merge_window_seconds >= 0",
    )

    op.drop_constraint(
        op.f("fk_staffing_cases_event_id_staffing_events"), "staffing_cases", type_="foreignkey"
    )
    op.drop_column("staffing_cases", "event_id")

    op.add_column(
        "staffing_events", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_staffing_events_processed_at_matches_status"),
        "staffing_events",
        "(status = 'RECEIVED') = (processed_at IS NULL)",
    )
    op.add_column("staffing_events", sa.Column("case_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_staffing_events_case_id_staffing_cases"),
        "staffing_events",
        "staffing_cases",
        ["case_id"],
        ["id"],
    )

    op.add_column("audit_log", sa.Column("event_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_audit_log_event_id_staffing_events"),
        "audit_log",
        "staffing_events",
        ["event_id"],
        ["id"],
    )


def downgrade() -> None:
    op.execute(REFUSE_EXISTING_ROWS_ON_DOWNGRADE)
    op.drop_constraint(
        op.f("fk_audit_log_event_id_staffing_events"), "audit_log", type_="foreignkey"
    )
    op.drop_column("audit_log", "event_id")

    op.drop_constraint(
        op.f("fk_staffing_events_case_id_staffing_cases"), "staffing_events", type_="foreignkey"
    )
    op.drop_column("staffing_events", "case_id")
    op.drop_constraint(
        op.f("ck_staffing_events_processed_at_matches_status"), "staffing_events", type_="check"
    )
    op.drop_column("staffing_events", "processed_at")

    op.add_column("staffing_cases", sa.Column("event_id", sa.BigInteger(), nullable=False))
    op.create_foreign_key(
        op.f("fk_staffing_cases_event_id_staffing_events"),
        "staffing_cases",
        "staffing_events",
        ["event_id"],
        ["id"],
    )

    op.drop_constraint(op.f("ck_shift_merge_window_seconds_non_negative"), "shift", type_="check")
    op.drop_column("shift", "merge_window_seconds")
