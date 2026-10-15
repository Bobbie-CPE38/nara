"""Gap time slices (round 4 PR T3).

Revision ID: c6e2b9f4a1d7
Revises: c4e8a2f6d1b3

STAFFING_GAP gets evaluated_from, and three child tables hold the headcount,
role and skill counts of each time slice of a gap. No backfill: a gap without
slices stays a whole-shift gap with its stored counts (docs/workflow.md 6.20).
"""

import sqlalchemy as sa
from alembic import op

revision = "c6e2b9f4a1d7"
down_revision = "c4e8a2f6d1b3"
branch_labels = None
depends_on = None

_COUNTS_VALID = (
    "required_count >= 0 AND current_count >= 0 "
    "AND gap_count = GREATEST(required_count - current_count, 0)"
)


def _slice_table(name: str, item_column: str | None, item_table: str | None) -> None:
    columns: list[sa.Column[object] | sa.Constraint] = [
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("gap_id", sa.BigInteger(), nullable=False),
    ]
    if item_column is not None:
        columns.append(sa.Column(item_column, sa.BigInteger(), nullable=False))
    columns += [
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("required_count", sa.Integer(), nullable=False),
        sa.Column("current_count", sa.Integer(), nullable=False),
        sa.Column("gap_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("start_at < end_at", name=op.f(f"ck_{name}_times_in_order")),
        sa.CheckConstraint(_COUNTS_VALID, name=op.f(f"ck_{name}_counts_valid")),
        sa.ForeignKeyConstraint(
            ["gap_id"], ["staffing_gap.id"], name=op.f(f"fk_{name}_gap_id_staffing_gap")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{name}")),
    ]
    unique = ["gap_id", "start_at"]
    if item_column is not None and item_table is not None:
        columns.append(
            sa.ForeignKeyConstraint(
                [item_column],
                [f"{item_table}.id"],
                name=op.f(f"fk_{name}_{item_column}_{item_table}"),
            )
        )
        unique = ["gap_id", item_column, "start_at"]
    columns.append(sa.UniqueConstraint(*unique, name=op.f(f"uq_{name}_gap_id")))
    op.create_table(name, *columns)
    op.create_index(op.f(f"ix_{name}_gap_id"), name, ["gap_id"])


def upgrade() -> None:
    op.add_column("staffing_gap", sa.Column("evaluated_from", sa.DateTime(timezone=True)))
    _slice_table("staffing_gap_interval", None, None)
    _slice_table("staffing_gap_role_interval", "role_id", "role")
    _slice_table("staffing_gap_skill_interval", "skill_id", "skill")


def downgrade() -> None:
    for name in (
        "staffing_gap_skill_interval",
        "staffing_gap_role_interval",
        "staffing_gap_interval",
    ):
        op.drop_index(op.f(f"ix_{name}_gap_id"), table_name=name)
        op.drop_table(name)
    op.drop_column("staffing_gap", "evaluated_from")
