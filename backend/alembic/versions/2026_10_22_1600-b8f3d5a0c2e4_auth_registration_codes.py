"""One-time LINE-bound web registration codes (round 6 AU5).

Revision ID: b8f3d5a0c2e4
Revises: a7e2c4f9b1d3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b8f3d5a0c2e4"
down_revision = "a7e2c4f9b1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_registration_code",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "staff_subject",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("staff.auth_subject", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("contact_id", sa.BigInteger(), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("line_uid_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("code_hash ~ '^[0-9a-f]{64}$'", name="code_hash_sha256_hex"),
        sa.CheckConstraint("line_uid_hash ~ '^[0-9a-f]{64}$'", name="uid_hash_sha256_hex"),
        sa.CheckConstraint("expires_at > created_at", name="time_order"),
    )
    op.create_index(
        "ix_auth_registration_code_staff_subject", "auth_registration_code", ["staff_subject"]
    )


def downgrade() -> None:
    op.drop_index("ix_auth_registration_code_staff_subject", table_name="auth_registration_code")
    op.drop_table("auth_registration_code")
