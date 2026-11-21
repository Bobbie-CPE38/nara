"""Round 6 PR EV9 migration e7b9d1f3a5c8: Supervisor queue capacity and system side rows."""

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core import clock
from app.db.models import ApprovalPolicy, ApprovalWardDecision
from app.domain.enums import ApprovalMode, ApprovalSide, ApproverCapacity
from app.seed.reset import ALEMBIC_INI
from tests.integration.case_rows import approval, short_case

REVISION = "e7b9d1f3a5c8"


def migration():
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION).module


def test_single_head_and_parent():
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert script.get_heads() == [REVISION]
    assert script.get_revision(REVISION).down_revision == "c3e5a7b9d1f2"


def test_upgrade_gives_existing_policies_the_supervisor_defaults(seeded):
    connection = seeded.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
        assert "supervisor_ratio" not in {
            row["name"] for row in inspect(connection).get_columns("approval_policy")
        }
        migration().upgrade()
    assert connection.execute(
        text("SELECT supervisor_ratio, supervisor_incoming_count FROM approval_policy")
    ).one() == (5, 10)


def decision(seeded, **values) -> ApprovalWardDecision:
    case, items = short_case(seeded, 105)
    request = approval(seeded, case, items[201])
    row = ApprovalWardDecision(
        approval_request_id=request.id,
        ward_id=1,
        side=ApprovalSide.DESTINATION,
        decided_as=ApproverCapacity.HEAD_NURSE,
        is_approved=True,
        decided_at=clock.now(),
    )
    for name, value in values.items():
        setattr(row, name, value)
    seeded.add(row)
    return row


@pytest.mark.parametrize(
    "values",
    [
        # A person's row without the person
        {"approval_mode": ApprovalMode.MANUAL, "approver_id": None},
        # A person's row with a queue
        {"approval_mode": ApprovalMode.MANUAL, "approver_id": 900, "queue_count": 3},
        # A system row naming a person
        {
            "approval_mode": ApprovalMode.AUTO,
            "approver_id": 900,
            "queue_count": 3,
            "queue_cap": 2,
            "queue_approver_count": 1,
        },
        # A system row without its queue, or with a queue that was not over its cap
        {"approval_mode": ApprovalMode.AUTO, "approver_id": None},
        {
            "approval_mode": ApprovalMode.AUTO,
            "approver_id": None,
            "queue_count": 2,
            "queue_cap": 2,
            "queue_approver_count": 1,
        },
        # The system never rejects
        {
            "approval_mode": ApprovalMode.AUTO,
            "approver_id": None,
            "is_approved": False,
            "queue_count": 3,
            "queue_cap": 2,
            "queue_approver_count": 1,
        },
    ],
)
def test_a_side_row_is_either_a_persons_or_the_systems(seeded, values):
    with pytest.raises(IntegrityError, match="mode_matches_decider"), seeded.begin_nested():
        decision(seeded, **values)
        seeded.flush()


def test_a_supervisor_capacity_cannot_be_negative(seeded):
    with pytest.raises(IntegrityError, match="supervisor_capacity_valid"), seeded.begin_nested():
        seeded.get(ApprovalPolicy, 1).supervisor_incoming_count = -1
        seeded.flush()


def test_downgrade_refuses_to_drop_system_decisions(seeded):
    decision(
        seeded,
        approval_mode=ApprovalMode.AUTO,
        approver_id=None,
        queue_count=3,
        queue_cap=2,
        queue_approver_count=1,
    )
    seeded.flush()
    connection = seeded.connection()
    with (
        Operations.context(MigrationContext.configure(connection)),
        pytest.raises(DBAPIError, match="Automatic ward decisions exist"),
        connection.begin_nested(),
    ):
        migration().downgrade()
