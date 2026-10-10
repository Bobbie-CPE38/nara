"""Offers and answers for the Golden Path; the orchestrator owns the transaction."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import CandidateItem, CandidateOutreach, CandidatePlan, StaffingCase
from app.domain.enums import (
    AuditAction,
    CandidateResponse,
    CaseStatus,
    Channel,
    EntityType,
    OutreachStatus,
)
from app.integrations.line import mock as line_mock
from app.schemas.outreach import OfferView
from app.services import audit_service


class OpenOfferConflictError(ValueError):
    """The responder has no unique open offer, or it differs from the expected ID."""


class UnsupportedResponseError(ValueError):
    """Rejection has no workflow transition in the walking skeleton yet."""


def list_offers(db: Session, *, staff_id: int) -> list[OfferView]:
    """Read the selected staff member's offer history by ID, without writing.

    Include all statuses and case status so the simulator can distinguish
    history from SENT offers on WAITING_RESPONSE cases. Selection is a demo
    read; record_response() still identifies the responder from X-Demo-User.
    No explicit flush, commit, audit or row lock.
    """
    rows = db.execute(
        select(
            CandidateOutreach.id,
            CandidateOutreach.case_id,
            CandidateOutreach.candidate_item_id,
            CandidateItem.staff_id,
            CandidateItem.proposed_shift_id,
            CandidateOutreach.status,
            StaffingCase.status.label("case_status"),
            CandidateOutreach.channel,
            CandidateOutreach.sent_at,
            CandidateOutreach.response_at,
        )
        .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
        .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
        .where(CandidateItem.staff_id == staff_id)
        .order_by(CandidateOutreach.id)
    ).mappings()
    return [OfferView.model_validate(row) for row in rows]


def send_offer(db: Session, case: StaffingCase) -> tuple[CandidateOutreach, int]:
    """Send exactly one rank-1 candidate from the latest plan, without committing.

    Returns the outreach and recipient staff ID; writes no audit row. The
    contact handler owns OFFER_SENT. Missing plans, missing rank-1 items, and
    duplicate rank-1 items raise. The handler lets these errors reach the
    orchestrator's D11 failure handling.
    Flush first because plans may have been created earlier in this round and
    production sessions have autoflush disabled.
    """
    db.flush()
    plan = db.scalar(
        select(CandidatePlan)
        .where(CandidatePlan.case_id == case.id)
        .order_by(CandidatePlan.id.desc())
        .limit(1)
    )
    if plan is None:
        raise LookupError(f"No candidate plan for case {case.id}")
    item = db.scalars(
        select(CandidateItem).where(CandidateItem.plan_id == plan.id, CandidateItem.rank == 1)
    ).one()
    outreach = CandidateOutreach(
        case_id=case.id,
        candidate_item_id=item.id,
        channel=Channel.LINE,
        status=OutreachStatus.SENT,
        sent_at=clock.now(),
    )
    db.add(outreach)
    db.flush()
    line_mock.send_offer(staff_id=item.staff_id, outreach_id=outreach.id)
    return outreach, item.staff_id


def get_accepted_outreach(db: Session, case_id: int) -> CandidateOutreach:
    """Return exactly one ACCEPTED outreach for the case (seam 4).

    Missing or multiple accepted offers raise NoResultFound / MultipleResultsFound
    for the safety handler to let D11 handle. Flush pending answers first because
    production sessions disable autoflush. Does not create rows, commit, audit,
    or acquire row locks. A flush error requires rollback before continuing.
    """
    db.flush()
    return db.scalars(
        select(CandidateOutreach).where(
            CandidateOutreach.case_id == case_id,
            CandidateOutreach.status == OutreachStatus.ACCEPTED,
        )
    ).one()


def record_response(
    db: Session, *, staff_id: int, actor_id: int, outreach_id: int, response: CandidateResponse
) -> tuple[CandidateOutreach, StaffingCase]:
    """Record ACCEPT and resume; leave commits and case status to the orchestrator.

    The caller supplies the authenticated staff ID and their actor ID. Exactly
    one SENT offer on a WAITING_RESPONSE case is required before checking
    that its ID matches outreach_id and whether the answer is supported.
    A mismatch raises before any answer, audit or workflow change. The ID never
    replaces staff authentication. Offers on other cases are ignored.
    Lock only outreach rows, in ID order, and refresh cached ORM state: a second
    request waits, then sees that the first request already answered the offer.
    Errors must propagate so the request session closes and rolls back, including
    any answer/audit flushed before an InvalidTransitionError from resume().
    """
    # Imported here because the orchestrator imports contact_candidate, which
    # uses this same service to send offers.
    from app.workflow import orchestrator

    if not isinstance(response, CandidateResponse):
        raise TypeError("response must be a CandidateResponse")
    offers = list(
        db.scalars(
            select(CandidateOutreach)
            .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
            .join(StaffingCase, StaffingCase.id == CandidateOutreach.case_id)
            .where(
                CandidateOutreach.status == OutreachStatus.SENT,
                CandidateItem.staff_id == staff_id,
                StaffingCase.status == CaseStatus.WAITING_RESPONSE,
            )
            .order_by(CandidateOutreach.id)
            .with_for_update(of=CandidateOutreach)
            .execution_options(populate_existing=True)
        )
    )
    if not offers:
        raise OpenOfferConflictError("No open offer for this staff member")
    if len(offers) != 1:
        raise OpenOfferConflictError("Expected exactly one open offer for this staff member")
    outreach = offers[0]
    if outreach.id != outreach_id:
        raise OpenOfferConflictError("The open offer has changed; refresh offers before responding")
    if response is CandidateResponse.REJECT:
        raise UnsupportedResponseError("REJECT is not supported in the walking skeleton")
    outreach.status = OutreachStatus.ACCEPTED
    outreach.response_at = clock.now()
    audit_service.log(
        db,
        case_id=outreach.case_id,
        actor_id=actor_id,
        action=AuditAction.OFFER_ACCEPTED,
        entity_type=EntityType.CANDIDATE_OUTREACH,
        entity_id=outreach.id,
        payload={"outreach_id": outreach.id, "staff_id": staff_id},
    )
    orchestrator.resume(db, outreach.case_id, CaseStatus.SAFETY_VALIDATION)
    case = db.get(StaffingCase, outreach.case_id)
    assert case is not None  # resume() already raises when the case is missing.
    return outreach, case
