"""H1 migration keeps the chain linear and enforces roster ownership in SQL."""

import io

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import RosterAssignment, StructuredHandover
from app.seed.reset import ALEMBIC_INI
from tests.integration.test_handover import created

REVISION = "e8c4b2a6f0d9"


def migration():
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION).module


def test_single_head_follows_attendance():
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1
    assert script.get_revision("f6b2d8a4c0e1").down_revision == REVISION
    assert script.get_revision(REVISION).down_revision == "a4d8e1b7c3f5"


def test_round_trip_preserves_existing_roster_and_attendance(seeded):
    connection = seeded.connection()
    roster_ids = list(seeded.scalars(select(RosterAssignment.id).order_by(RosterAssignment.id)))
    with Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
        assert "roster_assignment_id" not in {
            c["name"] for c in inspect(connection).get_columns("structured_handover")
        }
        migration().upgrade()
    assert (
        list(seeded.scalars(select(RosterAssignment.id).order_by(RosterAssignment.id)))
        == roster_ids
    )
    assert not next(
        c
        for c in inspect(connection).get_columns("structured_handover")
        if c["name"] == "roster_assignment_id"
    )["nullable"]


@pytest.mark.parametrize("invalid", ["duplicate", "missing_roster", "null"])
def test_constraints_reject_invalid_handover(production_seeded, invalid):
    db = production_seeded
    _, _, old = created(db)
    values = dict(
        case_id=old.case_id,
        shift_id=old.shift_id,
        incoming_staff_id=old.incoming_staff_id,
        roster_assignment_id=old.roster_assignment_id,
        content=old.content,
        generated_at=old.generated_at,
    )
    if invalid == "missing_roster":
        values["roster_assignment_id"] = 9999999
    elif invalid == "null":
        values["roster_assignment_id"] = None
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(StructuredHandover(**values))
        db.flush()


def test_unexpected_legacy_handover_is_refused_not_guessed(seeded):
    connection = seeded.connection()
    with Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
    # A stale or externally inserted row cannot be matched safely to a roster.
    from tests.integration.case_rows import make_case

    case = make_case(seeded)
    seeded.execute(
        text(
            "INSERT INTO structured_handover "
            "(case_id, shift_id, incoming_staff_id, content, generated_at) "
            "VALUES (:case, :shift, 201, '{}'::jsonb, now())"
        ),
        {"case": case.id, "shift": case.shift_id},
    )
    with (
        pytest.raises(IntegrityError),
        connection.begin_nested(),
        Operations.context(MigrationContext.configure(connection)),
    ):
        migration().upgrade()
    seeded.execute(text("DELETE FROM structured_handover"))
    with Operations.context(MigrationContext.configure(connection)):
        migration().upgrade()


def test_offline_sql_contains_required_constraints():
    out = io.StringIO()
    command.upgrade(Config(str(ALEMBIC_INI), output_buffer=out), "head", sql=True)
    sql = out.getvalue()
    assert "roster_assignment_id BIGINT NOT NULL" in sql
    assert "uq_structured_handover_roster_assignment_id" in sql
    assert "fk_structured_handover_roster_assignment_id_roster_assignment" in sql
