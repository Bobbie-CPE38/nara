"""
Offer cap of a staff member (docs/workflow.md, section 6.7).

The three Skeleton availability rules (not ACTIVE, already on the shift, on leave) were
replaced by the Hard Rules of domain/constraints (hard_rule_service) and removed in
round 1 PR 3. Only the offer cap is left here: it needs CANDIDATE_OUTREACH, so it is not
a Hard Rule.

Rules:
  * Read-only. Nothing here adds, flushes or commits.
  * Safety never calls staff_at_offer_limit(): the accepted candidate Safety checks
    always holds their own ACCEPTED offer.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CandidateItem, CandidateOutreach, StaffingCase
from app.domain.enums import AUTOMATION_STOPPED_STATUSES, OutreachStatus
from app.services import policy_service


def staff_at_offer_limit(db: Session, staff_ids: list[int]) -> set[int]:
    """Return requested staff IDs with SENT + ACCEPTED offers at or above the cap.

    Count offer rows across all running cases and plans, including accepted
    reserves. Offers on automation-stopped cases do not count. Read-only: the
    caller must flush changes it wants counted and own transaction control.

    Callers allocating offers must first lock the relevant STAFF rows in ID
    order (workflow.md 6.11), then recheck here in the same transaction. This
    query alone does not reserve capacity. The Solver calls it since PR 2a; wave
    selection follows in PR 2b. Safety must not call this helper on its own
    accepted offer.
    """
    if not staff_ids:
        return set()
    with db.no_autoflush:
        policy = policy_service.get_outreach_policy(db)
        return set(
            db.scalars(
                select(CandidateItem.staff_id)
                .join(CandidateOutreach, CandidateOutreach.candidate_item_id == CandidateItem.id)
                .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
                .where(
                    CandidateItem.staff_id.in_(staff_ids),
                    CandidateOutreach.status.in_([OutreachStatus.SENT, OutreachStatus.ACCEPTED]),
                    StaffingCase.status.not_in(list(AUTOMATION_STOPPED_STATUSES)),
                )
                .group_by(CandidateItem.staff_id)
                .having(
                    func.count(CandidateOutreach.id) >= policy.maximum_concurrent_offers_per_staff
                )
            )
        )
