"""Single-use LINE link codes and unique LINE ownership (round 3 PR K).

Revision ID: d7f0b3c5e9a2
Revises: c6e9a2b4d8f1

Duplicate legacy bindings must be resolved explicitly, never silently reassigned.
"""

import sqlalchemy as sa
from alembic import op

revision = "d7f0b3c5e9a2"
down_revision = "c6e9a2b4d8f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQL guard also works in `alembic upgrade head --sql`; no Python query result.
    op.execute("""DO $$ BEGIN
        IF EXISTS (
            SELECT 1 FROM contacts WHERE line_uid IS NOT NULL
            GROUP BY line_uid HAVING count(*) > 1
        ) THEN
            RAISE EXCEPTION 'Duplicate LINE bindings exist; resolve them before migration.';
        END IF;
    END $$""")
    op.create_unique_constraint(op.f("uq_contacts_line_uid"), "contacts", ["line_uid"])
    op.create_table(
        "line_account_link_code",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("staff_id", sa.BigInteger(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["staff_id"], ["staff.id"], name=op.f("fk_line_account_link_code_staff_id_staff")
        ),
        sa.UniqueConstraint("code_hash", name=op.f("uq_line_account_link_code_code_hash")),
        sa.CheckConstraint(
            "code_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_line_account_link_code_hash_format")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_line_account_link_code_positive_lifetime")
        ),
        sa.CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name=op.f("ck_line_account_link_code_single_terminal_state"),
        ),
    )
    op.create_index("ix_line_account_link_code_staff_id", "line_account_link_code", ["staff_id"])


def downgrade() -> None:
    op.drop_index("ix_line_account_link_code_staff_id", table_name="line_account_link_code")
    op.drop_table("line_account_link_code")
    op.drop_constraint(op.f("uq_contacts_line_uid"), "contacts", type_="unique")
