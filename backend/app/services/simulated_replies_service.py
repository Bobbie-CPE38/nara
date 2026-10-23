"""Scripted people of a test run (round 6 PR EV5a, docs/workflow.md 6.35.3).

A step of job_service.run_due_work(), so it runs on every job tick and after every
demo clock advance. It acts only while the clock belongs to an open run that asked
for simulated people (`auto_nurses`), and only on the offers and approval requests of
that run's case. Each answer goes through the same service as a person's: a nurse's
through outreach_service.record_response() (the LINE simulator's path), the source
ward head nurse's through approval_service.decide() (the Approvals page's path), in
that person's name and with payload.source SIMULATED. The time resolution is one job
tick (30 s) unless the clock is advanced.

An answer the service refuses is logged once and not tried again in that run: the
offer or request then waits for its timeout like an unanswered one, instead of a
new traceback on every tick.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from app.core import clock
from app.db.models import (
    ApprovalRequest,
    ApprovalWardDecision,
    AuditLog,
    CandidateItem,
    CandidateOutreach,
    Staff,
    StaffingEvent,
)
from app.domain.enums import (
    ApprovalSide,
    AuditAction,
    CandidateResponse,
    CheckInSource,
    EntityType,
    OutreachStatus,
)
from app.services import actor_service, approval_service, approval_wards, outreach_service

logger = logging.getLogger(__name__)

# (run ID, "offer" or "approval", row ID) of answers that failed. Process memory, like
# the clock that owns the run
_failed: set[tuple[int, str, int]] = set()

SIMULATED_SOURCE = CheckInSource.SIMULATED.value


@dataclass(frozen=True)
class Script:
    # Staff ID to (answer, seconds after their OFFER_SENT). Not listed: never answers
    nurses: dict[int, tuple[CandidateResponse, int]]
    # The source ward's head nurse and the seconds after APPROVAL_REQUESTED; None when
    # the scenario has no source side
    source_head_nurse: tuple[int, int] | None = None


# Delays stay under the 5-minute offer timeout. The order of the plan decides who is
# asked first; a script only says what each person would answer
SCRIPTS: dict[str, Script] = {
    # 203 never answers
    "golden": Script(
        nurses={
            202: (CandidateResponse.REJECT, 45),
            201: (CandidateResponse.ACCEPT, 120),
        },
    ),
    # Medicine can lend one person at a time, so these offers go one by one: the Float
    # Pool nurse declines, Niran accepts, 302 and 303 are never asked. Ratana (902),
    # Medicine's head nurse, approves her side
    "cross_ward": Script(
        nurses={
            401: (CandidateResponse.REJECT, 60),
            301: (CandidateResponse.ACCEPT, 120),
        },
        source_head_nurse=(902, 90),
    ),
}


def _scripted_run(db: Session) -> tuple[int, int, Script] | None:
    """The run, case and script of the open run that owns the clock, if it wants
    simulated people."""
    run_id = clock.test_run_id()
    if run_id is None:
        return None
    finished = aliased(AuditLog)
    started = db.scalars(
        select(AuditLog).where(
            AuditLog.id == run_id,
            AuditLog.action == AuditAction.TEST_RUN_STARTED,
            AuditLog.entity_type == EntityType.TEST_RUN,
            ~exists().where(
                finished.action == AuditAction.TEST_RUN_FINISHED,
                finished.entity_id == run_id,
            ),
        )
    ).one_or_none()
    if started is None or not started.payload.get("auto_nurses"):
        return None
    script = SCRIPTS.get(started.payload.get("scenario", ""))
    case_id = db.scalar(
        select(StaffingEvent.case_id).where(StaffingEvent.id == started.payload.get("event_id"))
    )
    if script is None or case_id is None:
        return None
    return run_id, case_id, script


def answer_due(db: Session) -> list[int]:
    """Give every scripted answer that is due now; return the offer and approval IDs
    answered. Commits through the services; a refused answer is logged and skipped."""
    scripted = _scripted_run(db)
    if scripted is None:
        return []
    run_id, case_id, script = scripted
    answered: list[int] = []
    now = clock.now()
    offers = db.execute(
        select(CandidateOutreach.id, CandidateItem.staff_id, CandidateOutreach.sent_at)
        .join(CandidateItem, CandidateItem.id == CandidateOutreach.candidate_item_id)
        .where(
            CandidateOutreach.case_id == case_id,
            CandidateOutreach.status == OutreachStatus.SENT,
        )
        .order_by(CandidateOutreach.id)
    ).all()
    for outreach_id, staff_id, sent_at in offers:
        line = script.nurses.get(staff_id)
        if line is None or sent_at is None:
            continue
        response, delay = line
        if sent_at + timedelta(seconds=delay) > now or (run_id, "offer", outreach_id) in _failed:
            continue
        try:
            outreach_service.record_response(
                db,
                staff_id=staff_id,
                actor_id=actor_service.user_id(db, staff_id),
                outreach_id=outreach_id,
                response=response,
                audit_source=SIMULATED_SOURCE,
            )
            answered.append(outreach_id)
        except Exception:
            db.rollback()
            _failed.add((run_id, "offer", outreach_id))
            logger.exception("Simulated answer of offer %s failed; not tried again", outreach_id)
    if script.source_head_nurse is not None:
        answered += _approve_source_side(db, run_id, case_id, *script.source_head_nurse)
    return answered


def _approve_source_side(
    db: Session, run_id: int, case_id: int, head_nurse_id: int, delay: int
) -> list[int]:
    head_nurse = db.get(Staff, head_nurse_id)
    if head_nurse is None:
        return []
    now = clock.now()
    decided = aliased(ApprovalWardDecision)
    requests = db.scalars(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.case_id == case_id,
            ApprovalRequest.is_pending.is_(True),
            ApprovalRequest.requested_at + timedelta(seconds=delay) <= now,
            ~exists().where(
                decided.approval_request_id == ApprovalRequest.id,
                decided.side == ApprovalSide.SOURCE,
            ),
        )
        .order_by(ApprovalRequest.id)
    ).all()
    answered = []
    for request in requests:
        item = db.get(CandidateItem, request.candidate_item_id)
        if item is None:
            continue
        wards = approval_wards.required_wards(db, item)
        if wards.get(ApprovalSide.SOURCE) != head_nurse.home_ward_id:
            continue
        request_id = request.id
        if (run_id, "approval", request_id) in _failed:
            continue
        try:
            approval_service.decide(
                db,
                approval_id=request_id,
                staff_id=head_nurse.id,
                role_id=head_nurse.role_id,
                home_ward_id=head_nurse.home_ward_id,
                actor_id=actor_service.user_id(db, head_nurse.id),
                approved=True,
                side=ApprovalSide.SOURCE.value,
                audit_source=SIMULATED_SOURCE,
            )
            answered.append(request_id)
        except Exception:
            db.rollback()
            _failed.add((run_id, "approval", request_id))
            logger.exception(
                "Simulated source approval of request %s failed; not tried again", request_id
            )
    return answered
