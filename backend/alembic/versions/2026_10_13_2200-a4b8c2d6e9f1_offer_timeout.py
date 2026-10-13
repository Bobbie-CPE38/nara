"""Add offer timeout policy and immutable per-offer expiry (round 1 PR O).

Revision ID: a4b8c2d6e9f1
Revises: f3a7c1d9e5b2

Existing policies adopt 300 seconds. Existing sent timestamps get that initial
expiry; answered rows without a sent timestamp remain nullable history. Abort
when a SENT row has no sent timestamp rather than inventing an offer lifetime.
New policies must supply the duration explicitly (no permanent server default).
"""

import sqlalchemy as sa
from alembic import op

revision = "a4b8c2d6e9f1"
down_revision = "f3a7c1d9e5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM candidate_outreach WHERE status = 'SENT' AND sent_at IS NULL) THEN
            RAISE EXCEPTION 'Cannot add expiry: repair SENT offers missing sent_at';
        END IF;
    END $$""")
    op.add_column(
        "outreach_policy",
        sa.Column("offer_timeout_seconds", sa.Integer(), nullable=False, server_default="300"),
    )
    op.alter_column("outreach_policy", "offer_timeout_seconds", server_default=None)
    op.create_check_constraint(
        op.f("ck_outreach_policy_offer_timeout_positive"),
        "outreach_policy",
        "offer_timeout_seconds > 0",
    )
    op.add_column(
        "candidate_outreach", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE candidate_outreach SET expires_at = sent_at + INTERVAL '300 seconds' "
        "WHERE sent_at IS NOT NULL"
    )
    op.create_check_constraint(
        op.f("ck_candidate_outreach_sent_has_expiry"),
        "candidate_outreach",
        "status != 'SENT' OR expires_at IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_candidate_outreach_sent_has_expiry"), "candidate_outreach", type_="check"
    )
    op.drop_column("candidate_outreach", "expires_at")
    op.drop_constraint(
        op.f("ck_outreach_policy_offer_timeout_positive"), "outreach_policy", type_="check"
    )
    op.drop_column("outreach_policy", "offer_timeout_seconds")
