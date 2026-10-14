"""Offer-attempt eligibility shared by Wave selection and case facts (round 2 PR T)."""

from sqlalchemy import exists, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import ApprovalRequest, CandidateItem, CandidateOutreach


def contactable_item(case_id: int) -> ColumnElement[bool]:
    """Uncontacted, or exactly one offer whose approval timed out.

    The caller separately checks current Hard Rules and the concurrent-offer cap.
    A skipped retry does not consume its allowance; sending the second row does.
    """
    count = (
        select(func.count(CandidateOutreach.id))
        .where(
            CandidateOutreach.case_id == case_id,
            CandidateOutreach.candidate_item_id == CandidateItem.id,
        )
        .correlate(CandidateItem)
        .scalar_subquery()
    )
    timed_out = (
        exists()
        .where(
            ApprovalRequest.case_id == case_id,
            ApprovalRequest.candidate_item_id == CandidateItem.id,
            ApprovalRequest.is_timed_out.is_(True),
            ApprovalRequest.outreach_id == CandidateOutreach.id,
            CandidateOutreach.case_id == case_id,
            CandidateOutreach.candidate_item_id == CandidateItem.id,
        )
        .correlate(CandidateItem)
    )
    return or_(count == 0, (count == 1) & timed_out)
