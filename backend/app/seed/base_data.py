"""System actors and stub policies for the walking skeleton.

Soft weights (all 1) are demo placeholders: the repository does not contain the
referenced v5 example values. The team's approval thresholds are ratio 2 and
incoming count 10. Auto-approval activates above twice the ward's required
nurse-to-patient ratio; incoming count refers to staff awaiting head nurse or
nurse supervisor approval. The count's comparison rule is still deferred.
The skeleton uses fixed candidates and MANUAL approval, not these parameters.
Hard policy maximum_patients_per_nurse (2) is used by the real gap calculator.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import Actor, ApprovalPolicy, HardConstraintPolicy, SoftConstraintPolicy
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
                candidate_count_weight=Decimal(1),
                consecutive_shift_weight=Decimal(1),
                workload_imbalance_weight=Decimal(1),
                projected_overtime_weight=Decimal(1),
                roster_change_weight=Decimal(1),
                candidate_source_priority=[source.value for source in CandidateSource],
                optimization_priority=[objective.value for objective in OptimizationObjective],
                effective_from=now,
                created_at=now,
            ),
            ApprovalPolicy(
                id=1,
                ratio=Decimal(2),
                incoming_count=10,
                version="demo-stub-v1",
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
        ],
    )
