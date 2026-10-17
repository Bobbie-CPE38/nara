"""Remember real reserve acceptance and independently deliver promotion notices."""

import sqlalchemy as sa
from alembic import op

revision = "c5f8b0d3e7a1"
down_revision = "b4e7a9c2d6f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidate_outreach",
        sa.Column("accepted_as_reserve", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Preserve currently waiting reserves without sending anything on upgrade.
    # This is the existing is_reserve rule, not the Solver's planned target.
    op.execute("""
        UPDATE candidate_outreach AS o SET accepted_as_reserve = true
        WHERE o.status = 'ACCEPTED'
          AND EXISTS (SELECT 1 FROM staffing_cases c WHERE c.id = o.case_id
              AND c.status NOT IN ('RESOLVED','FAILED','UNRESOLVED','MANUAL_HANDOFF'))
          AND NOT EXISTS (SELECT 1 FROM safety_validation s WHERE s.outreach_id = o.id)
          AND NOT EXISTS (SELECT 1 FROM approval_request a WHERE a.outreach_id = o.id)
    """)
    op.add_column(
        "offer_outcome_notification",
        sa.Column("kind", sa.Text(), nullable=False, server_default="FINAL"),
    )
    op.drop_constraint(
        "uq_offer_outcome_notification_outreach_id", "offer_outcome_notification", type_="unique"
    )
    op.create_unique_constraint(
        "uq_offer_outcome_notification_outreach_id",
        "offer_outcome_notification",
        ["outreach_id", "kind"],
    )
    op.create_check_constraint(
        op.f("ck_offer_outcome_notification_kind"),
        "offer_outcome_notification",
        "kind IN ('FINAL','RESERVE_PROMOTED')",
    )


def downgrade() -> None:
    # These are informational notices. Keep final outcomes and their UUIDs;
    # promotion history cannot fit the old one-row-per-offer schema.
    op.execute("DELETE FROM offer_outcome_notification WHERE kind = 'RESERVE_PROMOTED'")
    op.drop_constraint(
        op.f("ck_offer_outcome_notification_kind"), "offer_outcome_notification", type_="check"
    )
    op.drop_constraint(
        "uq_offer_outcome_notification_outreach_id", "offer_outcome_notification", type_="unique"
    )
    op.create_unique_constraint(
        "uq_offer_outcome_notification_outreach_id", "offer_outcome_notification", ["outreach_id"]
    )
    op.drop_column("offer_outcome_notification", "kind")
    op.drop_column("candidate_outreach", "accepted_as_reserve")
