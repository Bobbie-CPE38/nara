"""The migrations must build exactly the schema the models describe.

tests/conftest.py recreates the test database and runs `alembic upgrade head`
once per run, so these tests inspect what the migration files really produced.
"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

import app.db.models  # noqa: F401  registers all tables on Base.metadata
from app.db.base import Base
from app.db.session import engine

EXPECTED_TABLE_COUNT = 30  # docs/database-schema.md


def test_models_cover_every_table_in_the_schema_document() -> None:
    assert len(Base.metadata.tables) == EXPECTED_TABLE_COUNT


def test_migration_creates_every_model_table() -> None:
    with engine.connect() as connection:
        migrated = set(inspect(connection).get_table_names()) - {"alembic_version"}

    assert migrated == set(Base.metadata.tables)


def test_database_matches_the_models() -> None:
    """Same check as `alembic check`: a model change without a migration fails here."""
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, Base.metadata)

    assert differences == []


def test_relationship_constraints_exist() -> None:
    """The four constraints listed at the end of docs/database-schema.md.

    Alembic does not compare CHECK constraints, so they are asserted by name here.
    """
    with engine.connect() as connection:
        inspector = inspect(connection)
        actor_checks = {check["name"] for check in inspector.get_check_constraints("actors")}
        event_checks = {
            check["name"] for check in inspector.get_check_constraints("staffing_events")
        }
        actor_uniques = {unique["name"] for unique in inspector.get_unique_constraints("actors")}
        partial_index = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_actors_name_non_user'")
        ).scalar_one()

    assert "ck_actors_user_has_staff" in actor_checks
    assert "ck_staffing_events_staff_id_matches_event_group" in event_checks
    assert "uq_actors_staff_id" in actor_uniques
    assert "UNIQUE INDEX" in partial_index
    assert "WHERE (actor_type <> 'user'" in partial_index


def test_enum_columns_are_plain_text() -> None:
    """Enums are stored as text: no PostgreSQL ENUM type may be created."""
    with engine.connect() as connection:
        enum_types = inspect(connection).get_enums()

    assert enum_types == []
