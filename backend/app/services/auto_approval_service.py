"""Approve sides of requests whose approvers' queue is over its cap (workflow 6.22, 6.39).

Two queues decide, each on its own:

* The Head Nurse queue of a ward: every actionable request that still waits for that ward,
  on either side (the destination, or the source of a move). A request counts once per
  ward even when both of its sides are that ward. The cap is the lower of
  `APPROVAL_POLICY.ratio` x the ward's active Head Nurses and `incoming_count`.
* The Supervisor queue: every actionable request the Supervisor may already decide
  (`now >= supervisor_from`) with a side still waiting, once each. The cap is the lower of
  `supervisor_ratio` x the active Supervisors and `supervisor_incoming_count`; with no
  active Supervisor the queue never approves.

A queue over its cap (more than, not equal) approves the sides it covers: a ward's queue
its own ward's sides, the Supervisor queue every waiting side of its requests. The sides
of one request are decided one at a time through the same decision path as a person;
the request is executed only when its last required side is approved.

The caller must have no uncommitted writes. One snapshot holds the WARD row of the
destination of every actionable request, in ID order, so no person decides any of them
meanwhile; session commits in the shared decision path release savepoints, while the
caller's outer transaction retains the ward and full batch lock set. Cross-case
recomputes and LINE delivery wait until that outer commit.
"""

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from fractions import Fraction
from threading import Lock

from sqlalchemy import func, select
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import Select

from app.core import clock
from app.core.constants import HEAD_NURSE_ROLE, SUPERVISOR_ROLE
from app.db.models import (
    ApprovalRequest,
    ApprovalWardDecision,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    Role,
    RosterAssignment,
    Shift,
    Staff,
    StaffingCase,
)
from app.domain.enums import ApprovalSide, ApproverCapacity, StaffStatus
from app.services import (
    approval_service,
    hard_rule_service,
    line_delivery_service,
    outreach_service,
    policy_service,
)

logger = logging.getLogger(__name__)
# Process-local log throttling only; database locks coordinate concurrent jobs.
# HTTP job/clock requests may run in different threads, so protect bookkeeping.
MAX_FAILURE_KEYS = 1024  # Bound memory for distinct ward/exception pairs.
FAILURE_LOG_INTERVAL = 120  # First failure, then ~hourly at the default 30-second tick.
_failure_lock = Lock()
_failures: dict[tuple[frozenset[int], type[Exception]], int] = {}

# A move's source side first: the destination side completes the request and executes it
_SIDE_ORDER = (ApprovalSide.SOURCE, ApprovalSide.DESTINATION)


@dataclass
class AutomaticApprovals:
    """Requests with at least one side the system approved, and wards that must retry."""

    approval_ids: list[int] = field(default_factory=list)
    failed_ward_ids: set[int] = field(default_factory=set)


_PendingValues = tuple[int, int, datetime, int, int, int, int | None, int | None]
_source_shift = aliased(Shift)


def _pending() -> Select[*_PendingValues]:
    """Same actionable requests as the pending API, with the ward of each side."""
    return (
        select(
            ApprovalRequest.id,
            ApprovalRequest.case_id,
            ApprovalRequest.requested_at,
            CandidateItem.staff_id,
            StaffingCase.shift_id,
            Shift.ward_id,
            _source_shift.id.label("source_shift_id"),
            _source_shift.ward_id.label("source_ward_id"),
        )
        .select_from(ApprovalRequest)
        .join(CandidateItem, CandidateItem.id == ApprovalRequest.candidate_item_id)
        .join(StaffingCase, StaffingCase.id == ApprovalRequest.case_id)
        .join(Shift, Shift.id == StaffingCase.shift_id)
        .outerjoin(RosterAssignment, RosterAssignment.id == CandidateItem.source_assignment_id)
        .outerjoin(_source_shift, _source_shift.id == RosterAssignment.shift_id)
        .where(*approval_service.actionable_pending())
    )


def _waiting_sides(
    db: Session, rows: Sequence[Row[*_PendingValues]]
) -> dict[int, dict[ApprovalSide, int]]:
    """Each request's sides that no one has decided yet, with the ward of each."""
    decided = {
        (approval_id, side)
        for approval_id, side in db.execute(
            select(ApprovalWardDecision.approval_request_id, ApprovalWardDecision.side).where(
                ApprovalWardDecision.approval_request_id.in_([row.id for row in rows])
            )
        )
    }
    result: dict[int, dict[ApprovalSide, int]] = {}
    for row in rows:
        sides = {ApprovalSide.DESTINATION: row.ward_id}
        if row.source_ward_id is not None:
            sides[ApprovalSide.SOURCE] = row.source_ward_id
        result[row.id] = {
            side: ward for side, ward in sides.items() if (row.id, side) not in decided
        }
    return result


def _active(db: Session, role: str) -> dict[int, int]:
    """Active staff of a role per home ward."""
    return {
        ward_id: count
        for ward_id, count in db.execute(
            select(Staff.home_ward_id, func.count())
            .join(Role, Role.id == Staff.role_id)
            .where(Staff.status == StaffStatus.ACTIVE, Role.name == role)
            .group_by(Staff.home_ward_id)
        )
    }


def plan_sides(
    db: Session, rows: Sequence[Row[*_PendingValues]]
) -> dict[tuple[int, ApprovalSide], approval_service.AutoSide]:
    """The sides each queue over its cap may approve now, from one snapshot (6.39)."""
    policy = policy_service.get_approval_policy(db)
    if (
        policy.ratio < 0
        or policy.incoming_count < 0
        or policy.supervisor_ratio < 0
        or policy.supervisor_incoming_count < 0
    ):
        raise ValueError("Approval capacity cannot be negative")
    waiting = _waiting_sides(db, rows)
    planned: dict[tuple[int, ApprovalSide], approval_service.AutoSide] = {}

    # Head Nurse queues: a request once per ward that still has to decide it
    queues: dict[int, set[int]] = defaultdict(set)
    for approval_id, sides in waiting.items():
        for ward_id in sides.values():
            queues[ward_id].add(approval_id)
    heads = _active(db, HEAD_NURSE_ROLE)
    for ward_id, approval_ids in queues.items():
        approvers = heads.get(ward_id, 0)
        cap = min(Fraction(policy.ratio) * approvers, Fraction(policy.incoming_count))
        if len(approval_ids) <= cap:
            continue
        basis = approval_service.AutoSide(
            ApproverCapacity.HEAD_NURSE, len(approval_ids), cap, approvers
        )
        for approval_id in approval_ids:
            for side, side_ward in waiting[approval_id].items():
                if side_ward == ward_id:
                    planned[(approval_id, side)] = basis

    # The Supervisor queue: requests past supervisor_from, once each, never with nobody
    supervisors = sum(_active(db, SUPERVISOR_ROLE).values())
    if supervisors > 0:
        since = clock.now() - timedelta(seconds=policy.supervisor_after_seconds)
        due = [row.id for row in rows if row.requested_at <= since and waiting[row.id]]
        cap = min(
            Fraction(policy.supervisor_ratio) * supervisors,
            Fraction(policy.supervisor_incoming_count),
        )
        if len(due) > cap:
            basis = approval_service.AutoSide(
                ApproverCapacity.SUPERVISOR, len(due), cap, supervisors
            )
            for approval_id in due:
                for side in waiting[approval_id]:
                    # A side its ward's own queue already covers keeps that reason
                    planned.setdefault((approval_id, side), basis)
    return planned


def _lock_batch(db: Session, rows: Sequence[Row[*_PendingValues]]) -> None:
    """Prelock the union before any decision: never take another Shift after Staff."""
    shift_ids = {row.shift_id for row in rows} | {
        row.source_shift_id for row in rows if row.source_shift_id is not None
    }
    approval_ids = {row.id for row in rows}
    case_ids = {row.case_id for row in rows}
    staff_ids = {row.staff_id for row in rows}
    list(
        db.scalars(
            select(Shift)
            .where(Shift.id.in_(shift_ids))
            .order_by(Shift.id)
            .with_for_update(key_share=True)
        )
    )
    list(
        db.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.id.in_(approval_ids))
            .order_by(ApprovalRequest.id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
    )
    query = approval_service.decision_offers_query(case_ids, staff_ids)
    offers = list(
        db.scalars(
            query.order_by(CandidateOutreach.id)
            .with_for_update(key_share=True, of=CandidateOutreach)
            .execution_options(populate_existing=True)
        )
    )
    list(
        db.scalars(
            select(StaffingCase)
            .where(StaffingCase.id.in_(case_ids))
            .order_by(StaffingCase.id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
    )
    plan_staff = set(
        db.scalars(
            select(CandidateItem.staff_id)
            .join(CandidatePlan, CandidatePlan.id == CandidateItem.plan_id)
            .where(CandidatePlan.case_id.in_(case_ids))
        )
    )
    hard_rule_service.lock_staff(db, plan_staff | staff_ids)
    current = set(db.scalars(query.with_only_columns(CandidateOutreach.id)))
    if not current <= {offer.id for offer in offers}:
        raise approval_service.ApprovalLockRetryError("Offer set changed while locking the batch")


def _snapshot(db: Session, ward_ids: Sequence[int]) -> list[int]:
    notifications: list[tuple[int, int, tuple[int, ...]]] = []
    deliveries: set[int | None] = set()
    decided: list[int] = []
    # db's transaction is the outer owner. The batch Session only owns savepoints.
    connection = db.connection()
    with Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    ) as batch:
        # Every destination ward in ID order: a person deciding any of these requests
        # takes its destination ward first, so the snapshot cannot change under us
        for ward_id in ward_ids:
            approval_service.lock_ward_row(batch, ward_id)
        pending = list(
            batch.execute(_pending().order_by(ApprovalRequest.requested_at, ApprovalRequest.id))
        )
        if not {row.ward_id for row in pending} <= set(ward_ids):
            # A request of another ward arrived since the wards were read: lock it too
            raise approval_service.ApprovalLockRetryError("A new destination ward appeared")
        planned = plan_sides(batch, pending)
        eligible = [row for row in pending if any(key[0] == row.id for key in planned)]
        if not eligible:
            batch.rollback()
            db.rollback()
            return []
        _lock_batch(batch, eligible)
        transaction = connection.get_transaction()
        assert transaction is not None
        authorization = approval_service.AutoApprovalBatch(
            frozenset(ward_ids), planned, connection, transaction
        )
        batch.info["line_delivery_scheduler"] = deliveries.add
        for row in eligible:
            for side in _SIDE_ORDER:
                if (row.id, side) not in planned:
                    continue
                try:
                    approval_service.decide_automatic(
                        batch,
                        approval_id=row.id,
                        side=side,
                        batch=authorization,
                        notifications=notifications,
                    )
                except (
                    approval_service.ApprovalNotPendingError,
                    approval_service.ApprovalOfferConflictError,
                ):
                    # Another approval in this snapshot can have closed this case or
                    # cancelled its offer, or the candidate no longer passes the hard
                    # rules. No writes precede these refusals; the request is left as it is.
                    break
                if not decided or decided[-1] != row.id:
                    decided.append(row.id)
        batch.commit()
    db.commit()
    db.expire_all()
    # These operations can acquire a different case's locks, so run them only
    # after the complete transaction has released its lock set.
    for staff_id, case_id, foreign in notifications:
        try:
            outreach_service.recompute_affected_cases(
                db,
                staff_id=staff_id,
                own_case_id=case_id,
                additional_case_ids=foreign,
            )
        except Exception:
            db.rollback()
            logger.exception(
                "Best-effort auto-approval foreign-case recompute failed for case %s; "
                "no queued retry",
                case_id,
            )
    for delivery_case_id in deliveries:
        try:
            line_delivery_service.dispatch_pending(db, case_id=delivery_case_id)
        except Exception:
            db.rollback()
            logger.exception(
                "Auto-approval LINE dispatch failed; durable offer intents remain "
                "for the next job sweep"
            )
    return decided


def approve_due_requests(db: Session) -> AutomaticApprovals:
    """No caller writes. One locked snapshot of every ward per tick; it retries next tick."""
    result = AutomaticApprovals()
    wards: list[int] = []
    for attempt in range(5):
        wards = sorted(set(db.scalars(_pending().with_only_columns(Shift.ward_id))))
        db.rollback()
        if not wards:
            return result
        try:
            result.approval_ids.extend(_snapshot(db, wards))
            with _failure_lock:
                for key in [key for key in _failures if key[0] & set(wards)]:
                    del _failures[key]
            return result
        except approval_service.ApprovalLockRetryError:
            db.rollback()
            if attempt < 4:
                continue
            result.failed_ward_ids.update(wards)
        except Exception as error:
            db.rollback()
            key = (frozenset(wards), type(error))
            with _failure_lock:
                if len(_failures) >= MAX_FAILURE_KEYS and key not in _failures:
                    del _failures[next(iter(_failures))]
                _failures[key] = _failures.get(key, 0) + 1
                should_log = _failures[key] == 1 or _failures[key] % FAILURE_LOG_INTERVAL == 0
            if should_log:
                logger.exception("Auto-approval for wards %s failed; retry next tick", wards)
            result.failed_ward_ids.update(wards)
        break
    return result
