"""Permanent staff subject, web accounts and sessions (round 6 PR AU1).

docs/workflow.md 6.33.2 and docs/database-schema.md (AU0 section). Every existing staff
row gets a random subject once. No account is created: STAFF.password_hash ("!" in the
seed) is not copied, so no password works after this migration until the account
script sets one.

Revision ID: a7e2c4f9b1d3
Revises: f9a1c3e5b7d2
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7e2c4f9b1d3"
down_revision = "f9a1c3e5b7d2"
branch_labels = None
depends_on = None

IMMUTABLE_FUNCTION = "staff_auth_subject_immutable"


def upgrade() -> None:
    # The default fills the existing rows, then goes: the application supplies the value
    op.add_column(
        "staff",
        sa.Column(
            "auth_subject",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
    )
    op.alter_column("staff", "auth_subject", server_default=None)
    op.create_unique_constraint(op.f("uq_staff_auth_subject"), "staff", ["auth_subject"])
    # Immutable in the database too, so no code path can hand a subject to someone else
    op.execute(
        f"""
        CREATE FUNCTION {IMMUTABLE_FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'staff.auth_subject cannot change'
                USING ERRCODE = 'integrity_constraint_violation';
        END
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {IMMUTABLE_FUNCTION} BEFORE UPDATE OF auth_subject ON staff
        FOR EACH ROW WHEN (OLD.auth_subject IS DISTINCT FROM NEW.auth_subject)
        EXECUTE FUNCTION {IMMUTABLE_FUNCTION}()
        """
    )

    op.create_table(
        "auth_account",
        sa.Column(
            "staff_subject",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "staff.auth_subject",
                name=op.f("fk_auth_account_staff_subject_staff"),
                ondelete="RESTRICT",
            ),
            primary_key=True,
        ),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.Column("credential_version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("staff_subject", name=op.f("pk_auth_account")),
        sa.CheckConstraint(
            "credential_version > 0", name=op.f("ck_auth_account_credential_version_positive")
        ),
    )
    op.create_table(
        "auth_session",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "account_subject",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "auth_account.staff_subject",
                name=op.f("fk_auth_session_account_subject_auth_account"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("credential_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_session_token_hash")),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_auth_session_token_hash_sha256_hex")
        ),
        sa.CheckConstraint(
            "credential_version > 0", name=op.f("ck_auth_session_credential_version_positive")
        ),
        sa.CheckConstraint(
            "created_at <= last_seen_at AND last_seen_at <= expires_at AND expires_at > created_at",
            name=op.f("ck_auth_session_time_order"),
        ),
    )
    op.create_index(op.f("ix_auth_session_account_subject"), "auth_session", ["account_subject"])


def downgrade() -> None:
    # Accounts and sessions are lost; the subjects go with the column
    op.drop_index(op.f("ix_auth_session_account_subject"), table_name="auth_session")
    op.drop_table("auth_session")
    op.drop_table("auth_account")
    op.execute(f"DROP TRIGGER {IMMUTABLE_FUNCTION} ON staff")
    op.execute(f"DROP FUNCTION {IMMUTABLE_FUNCTION}()")
    op.drop_constraint(op.f("uq_staff_auth_subject"), "staff", type_="unique")
    op.drop_column("staff", "auth_subject")
