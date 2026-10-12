"""Add the Solver's target rows, the snapshot link and the source weight (round 1 PR 2a).

Revision ID: f3a7c1d9e5b2
Revises: d91a6c8e203f

Round 1 contract, section 8.3.
  * candidate_item_target: the targets a candidate was selected to fill (Q55).
  * candidate_items.working_time_snapshot_id: the snapshot the Solver ranked the
    candidate with. NULL on rows written before this revision.
  * soft_constraint_policy.candidate_source_weight: weight of the source term of
    plan_penalty. Existing policies are backfilled with 200, the agreed seed
    value. The temporary default is removed so new versions supply their own.
"""

import sqlalchemy as sa
from alembic import op

revision = "f3a7c1d9e5b2"
down_revision = "d91a6c8e203f"
branch_labels = None
depends_on = None

SNAPSHOT_FK = "fk_candidate_items_working_time_snapshot_id_staff_working_time_snapshot"


def upgrade() -> None:
    op.add_column(
        "soft_constraint_policy",
        sa.Column("candidate_source_weight", sa.Numeric(), nullable=False, server_default="200"),
    )
    op.alter_column("soft_constraint_policy", "candidate_source_weight", server_default=None)
    op.add_column(
        "candidate_items",
        sa.Column("working_time_snapshot_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        op.f(SNAPSHOT_FK),
        "candidate_items",
        "staff_working_time_snapshot",
        ["working_time_snapshot_id"],
        ["id"],
    )
    op.create_table(
        "candidate_item_target",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("candidate_item_id", sa.BigInteger(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=True),
        sa.Column("skill_id", sa.BigInteger(), nullable=True),
        sa.Column("selection_type", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(target_type = 'ROLE') = (role_id IS NOT NULL)",
            name=op.f("ck_candidate_item_target_role_id_matches_target_type"),
        ),
        sa.CheckConstraint(
            "(target_type = 'SKILL') = (skill_id IS NOT NULL)",
            name=op.f("ck_candidate_item_target_skill_id_matches_target_type"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_item_id"],
            ["candidate_items.id"],
            name=op.f("fk_candidate_item_target_candidate_item_id_candidate_items"),
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["role.id"], name=op.f("fk_candidate_item_target_role_id_role")
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skill.id"], name=op.f("fk_candidate_item_target_skill_id_skill")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_item_target")),
    )


def downgrade() -> None:
    op.drop_table("candidate_item_target")
    # Dropping the column also drops its foreign key
    op.drop_column("candidate_items", "working_time_snapshot_id")
    op.drop_column("soft_constraint_policy", "candidate_source_weight")
