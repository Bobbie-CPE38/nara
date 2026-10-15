"""Drain an overloaded ward's eligible snapshot in one transaction (workflow 6.22).

The caller must have no uncommitted writes. Session commits in decide() release
savepoints, while the caller's outer transaction retains the ward and full batch
lock set. Cross-case recomputes and LINE delivery wait until that outer commit.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction

from sqlalchemy import func, select
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core import clock
from app.core.constants import HEAD_NURSE_ROLE
from app.db.models import (
    ApprovalRequest,
    CandidateItem,
    CandidateOutreach,
    CandidatePlan,
    Role,
    Shift,
    Staff,
    StaffingCase,
    Ward,
)
from app.domain.enums import AUTOMATION_STOPPED_STATUSES, CandidateSource, StaffStatus
from app.services import (
    approval_service,
    case_facts_service,
    hard_rule_service,
    line_delivery_service,
    outreach_service,
    policy_service,
)

logger = logging.getLogger(__name__)
_failures: dict[tuple[int, type[Exception]], int] = {}


@dataclass
class AutomaticApprovals:
    approval_ids: list[int] = field(default_factory=list)
    failed_ward_ids: set[int] = field(default_factory=set)


_PendingValues = tuple[int, int, datetime, int, CandidateSource, int | None, int, int]


def _pending() -> Select[*_PendingValues]:
    """Same actionable requests as the pending API, including manual-only candidates."""
    return (
        select(
            ApprovalRequest.id,
            ApprovalRequest.case_id,
            ApprovalRequest.requested_at,
            CandidateItem.staff_id,
            CandidateItem.source,
            CandidateItem.source_assignment_id,
            StaffingCase.shift_id,
            Shift.ward_id,
        )
        .select_from(ApprovalRequest)
        .join(CandidateItem, CandidateItem.id == ApprovalRequest.candidate_item_id)
        .join(StaffingCase, StaffingCase.id == ApprovalRequest.case_id)
        .join(Shift, Shift.id == StaffingCase.shift_id)
        .where(
            ApprovalRequest.is_pending.is_(True),
            ApprovalRequest.expires_at > clock.now(),
            StaffingCase.status.not_in(list(AUTOMATION_STOPPED_STATUSES)),
            case_facts_service.accepted_offer_for_request(),
        )
    )


def _lock_batch(db: Session, rows: Sequence[Row[*_PendingValues]]) -> None:
    """Prelock the union before any decision: never take another Shift after Staff."""
    shift_ids = {row.shift_id for row in rows}
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


def _ward(db: Session, ward_id: int) -> list[int]:
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
        batch.scalars(select(Ward).where(Ward.id == ward_id).with_for_update(key_share=True)).one()
        pending = list(
            batch.execute(
                _pending()
                .where(Shift.ward_id == ward_id)
                .order_by(ApprovalRequest.requested_at, ApprovalRequest.id)
            )
        )
        approvers = (
            batch.scalar(
                select(func.count())
                .select_from(Staff)
                .join(Role, Role.id == Staff.role_id)
                .where(
                    Staff.home_ward_id == ward_id,
                    Staff.status == StaffStatus.ACTIVE,
                    Role.name == HEAD_NURSE_ROLE,
                )
            )
            or 0
        )
        policy = policy_service.get_approval_policy(batch)
        if policy.ratio < 0 or policy.incoming_count < 0:
            raise ValueError("Approval capacity cannot be negative")
        cap = min(Fraction(policy.ratio) * approvers, Fraction(policy.incoming_count))
        if len(pending) <= cap:
            batch.rollback()
            db.rollback()
            return []
        eligible = [
            row
            for row in pending
            if row.source == CandidateSource.SAME_WARD and row.source_assignment_id is None
        ]
        if not eligible:
            batch.rollback()
            db.rollback()
            return []
        _lock_batch(batch, eligible)
        transaction = connection.get_transaction()
        assert transaction is not None
        batch.info["auto_approval_batch"] = approval_service.AutoApprovalBatch(
            ward_id,
            len(pending),
            approvers,
            cap,
            frozenset(row.id for row in eligible),
            connection,
            transaction,
        )
        batch.info["line_delivery_scheduler"] = deliveries.add
        batch.info["approval_notification_scheduler"] = lambda staff_id, case_id, foreign: (
            notifications.append((staff_id, case_id, foreign))
        )
        for row in eligible:
            try:
                request, case = approval_service.decide(
                    batch,
                    approval_id=row.id,
                    staff_id=None,
                    role_id=None,
                    home_ward_id=None,
                    actor_id=0,
                    approved=True,
                    automatic=True,
                )
                decided.append(request.id)
            except (
                approval_service.ApprovalNotPendingError,
                approval_service.ApprovalOfferConflictError,
            ):
                # Another approval in this snapshot can have closed this case or
                # cancelled its offer. No writes precede these business refusals.
                continue
        batch.commit()
    db.commit()
    db.expire_all()
    # These operations can acquire a different case's locks, so run them only
    # after the complete ward transaction has released its lock set.
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
            logger.exception("Auto-approval foreign-case recompute deferred for case %s", case_id)
    for delivery_case_id in deliveries:
        try:
            line_delivery_service.dispatch_pending(db, case_id=delivery_case_id)
        except Exception:
            db.rollback()
            logger.exception("Auto-approval LINE delivery deferred")
    return decided


def approve_due_requests(db: Session) -> AutomaticApprovals:
    """No caller writes. Each ward commits independently; locked facts are authoritative."""
    wards = sorted(set(db.scalars(_pending().with_only_columns(Shift.ward_id))))
    db.rollback()
    result = AutomaticApprovals()
    for ward_id in wards:
        for attempt in range(5):
            try:
                result.approval_ids.extend(_ward(db, ward_id))
                for key in [key for key in _failures if key[0] == ward_id]:
                    del _failures[key]
                break
            except approval_service.ApprovalLockRetryError:
                db.rollback()
                if attempt < 4:
                    continue
                result.failed_ward_ids.add(ward_id)
            except Exception as error:
                db.rollback()
                key = (ward_id, type(error))
                if len(_failures) >= 1024 and key not in _failures:
                    del _failures[next(iter(_failures))]
                _failures[key] = _failures.get(key, 0) + 1
                if _failures[key] == 1 or _failures[key] % 120 == 0:
                    logger.exception("Auto-approval for ward %s failed; retry next tick", ward_id)
                result.failed_ward_ids.add(ward_id)
            break
    return result
