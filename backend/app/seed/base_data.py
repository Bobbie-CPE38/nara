"""System actors and stub policies for the walking skeleton.

Soft weights follow the priorities of round 6 PR EV6 (docs/workflow.md 6.36.7): one more
candidate costs 40000, more than everything else one person can cost, so the smallest group
wins; then a moved assignment, the source, each hour of the week, each consecutive shift and
the projected overtime, one step of each above the whole range of the ones after it.
The team's approval thresholds are ratio 2 and
incoming count 10. From round 4, ratio is the number of pending requests one
active head nurse can handle, and incoming count is the hard cap on a ward's
queue: auto-approval starts when the ward's pending requests exceed
min(ratio x active head nurses, incoming count) (workflow 6.22, round 4 PR A).
Requests begin MANUAL; the due-work job may auto-approve an overloaded queue.
Hard policy maximum_patients_per_nurse (2) is the ratio behind the seeded
required_staff of each shift. The gap reads required_staff, not the ratio;
required_staff_for() applies the ratio and has no caller in app code until the
merge window (round 1 PR M). preserve_minimum_staffing is read by the gap.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    Actor,
    ApprovalPolicy,
    HardConstraintPolicy,
    OutreachPolicy,
    SoftConstraintPolicy,
)
from app.domain.enums import ActorName, ActorType, CandidateSource, OptimizationObjective
from app.seed import sync_sequences


def seed(db: Session) -> None:
    """Insert base data into a fresh database; flush but never commit."""
    now = clock.now()
    db.add_all(
        Actor(
            name=name.value,
            actor_type=ActorType.SYSTEM if name is ActorName.SYSTEM else ActorType.COMPONENT,
            staff_id=None,
        )
        for name in ActorName
    )
    db.add_all(
        [
            HardConstraintPolicy(
                id=1,
                version="demo-stub-v1",
                minimum_rest_hours=Decimal(11),
                maximum_daily_hours=Decimal(12),
                maximum_weekly_hours=Decimal(52),
                maximum_consecutive_shifts=7,
                maximum_patients_per_nurse=Decimal(2),
                prevent_shift_conflict=True,
                require_matching_role=True,
                require_matching_skill=True,
                require_active_staff=True,
                preserve_minimum_staffing=True,
                preserve_source_ward_minimum=True,
                effective_from=now,
                created_at=now,
            ),
            SoftConstraintPolicy(
                id=1,
                version="demo-stub-v1",
                # Round 6 PR EV6 (6.36.7): one step of each priority (a person, a moved
                # assignment, a source, an hour of the week, a consecutive shift) outweighs
                # the whole range of the ones below it for one person
                candidate_count_weight=Decimal(40000),
                consecutive_shift_weight=Decimal(17),
                workload_imbalance_weight=Decimal(120),
                projected_overtime_weight=Decimal(1),
                roster_change_weight=Decimal(20000),
                candidate_source_weight=Decimal(6400),
                candidate_source_priority=[source.value for source in CandidateSource],
                optimization_priority=[
                    OptimizationObjective.MIN_CANDIDATE_COUNT.value,
                    OptimizationObjective.CANDIDATE_SOURCE.value,
                    OptimizationObjective.WEEKLY_WORKLOAD_FAIRNESS.value,
                    OptimizationObjective.MIN_CONSECUTIVE_SHIFT.value,
                    OptimizationObjective.MIN_PROJECTED_OVERTIME.value,
                ],
                solver_time_limit_seconds=3,
                effective_from=now,
                created_at=now,
            ),
            ApprovalPolicy(
                id=1,
                ratio=Decimal(2),
                incoming_count=10,
                version="demo-stub-v1",
                created_at=now,
                approval_timeout_seconds=900,
                supervisor_after_seconds=600,
            ),
            OutreachPolicy(
                id=1,
                maximum_concurrent_offers_per_staff=3,
                offer_timeout_seconds=300,
                # Round 6 PR EV6 (6.36.8): 10 waves, 90 minutes from the opening of the case
                maximum_waves_per_case=10,
                case_outreach_deadline_seconds=90 * 60,
                version="demo-outreach-v1",
                effective_from=now,
                created_at=now,
            ),
        ]
    )
    sync_sequences(
        db,
        [
            HardConstraintPolicy.__tablename__,
            SoftConstraintPolicy.__tablename__,
            ApprovalPolicy.__tablename__,
            OutreachPolicy.__tablename__,
        ],
    )
