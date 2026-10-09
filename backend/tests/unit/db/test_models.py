"""Models owned by person 1 must match docs/database-schema.md exactly."""

import pytest
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateIndex, CreateTable

import app.db.models  # noqa: F401  registers all tables on Base.metadata
from app.db.base import Base
from app.db.types import StrEnumText

NOT_NULL = False
NULL = True

# table -> column -> (type, nullable), copied from docs/database-schema.md
EXPECTED: dict[str, dict[str, tuple[type, bool]]] = {
    "staff": {
        "id": (BigInteger, NOT_NULL),
        "first_name": (Text, NOT_NULL),
        "last_name": (Text, NOT_NULL),
        "email": (Text, NOT_NULL),
        "password_hash": (Text, NOT_NULL),
        "role_id": (BigInteger, NOT_NULL),
        "home_ward_id": (BigInteger, NOT_NULL),
        "status": (StrEnumText, NOT_NULL),
        "created_at": (DateTime, NOT_NULL),
        "updated_at": (DateTime, NOT_NULL),
    },
    "actors": {
        "id": (BigInteger, NOT_NULL),
        "name": (Text, NOT_NULL),
        "actor_type": (StrEnumText, NOT_NULL),
        "staff_id": (BigInteger, NULL),
    },
    "ward": {
        "id": (BigInteger, NOT_NULL),
        "name": (Text, NOT_NULL),
        "created_at": (DateTime, NOT_NULL),
        "updated_at": (DateTime, NOT_NULL),
        "deactivated_at": (DateTime, NULL),
        "is_active": (Boolean, NOT_NULL),
    },
    "skill": {
        "id": (BigInteger, NOT_NULL),
        "name": (Text, NOT_NULL),
    },
    "role": {
        "id": (BigInteger, NOT_NULL),
        "name": (Text, NOT_NULL),
    },
    "staff_skill": {
        "staff_id": (BigInteger, NOT_NULL),
        "skill_id": (BigInteger, NOT_NULL),
    },
    "shift": {
        "id": (BigInteger, NOT_NULL),
        "ward_id": (BigInteger, NOT_NULL),
        "patient_count": (Integer, NOT_NULL),
        "start_at": (DateTime, NOT_NULL),
        "end_at": (DateTime, NOT_NULL),
        "shift_type": (StrEnumText, NOT_NULL),
        "is_active": (Boolean, NOT_NULL),
        "deactivated_at": (DateTime, NULL),
    },
    "staffing_events": {
        "id": (BigInteger, NOT_NULL),
        "event_type": (StrEnumText, NOT_NULL),
        "shift_id": (BigInteger, NOT_NULL),
        "occurred_at": (DateTime, NOT_NULL),
        "staff_id": (BigInteger, NULL),
        "payload": (JSONB, NOT_NULL),
        "status": (StrEnumText, NOT_NULL),
    },
    "staffing_requirements": {
        "id": (BigInteger, NOT_NULL),
        "shift_id": (BigInteger, NOT_NULL),
        "required_staff": (Integer, NOT_NULL),
        "minimum_staff": (Integer, NOT_NULL),
        "created_at": (DateTime, NOT_NULL),
    },
    "staffing_requirement_role": {
        "staffing_requirement_id": (BigInteger, NOT_NULL),
        "role_id": (BigInteger, NOT_NULL),
        "required_count": (Integer, NOT_NULL),
    },
    "staffing_requirement_skill": {
        "staffing_requirement_id": (BigInteger, NOT_NULL),
        "skill_id": (BigInteger, NOT_NULL),
        "required_count": (Integer, NOT_NULL),
    },
    "staffing_cases": {
        "id": (BigInteger, NOT_NULL),
        "event_id": (BigInteger, NOT_NULL),
        "shift_id": (BigInteger, NOT_NULL),
        "status": (StrEnumText, NOT_NULL),
        "required_replacement_time": (DateTime, NOT_NULL),
        "created_at": (DateTime, NOT_NULL),
        "updated_at": (DateTime, NOT_NULL),
    },
    "staff_unavailability": {
        "id": (BigInteger, NOT_NULL),
        "staff_id": (BigInteger, NOT_NULL),
        "start_at": (DateTime, NOT_NULL),
        "end_at": (DateTime, NULL),
        "reason": (StrEnumText, NOT_NULL),
    },
    "roster_assignment": {
        "id": (BigInteger, NOT_NULL),
        "staff_id": (BigInteger, NOT_NULL),
        "shift_id": (BigInteger, NOT_NULL),
        "status": (StrEnumText, NOT_NULL),
        "assignment_type": (StrEnumText, NOT_NULL),
        "candidate_source": (StrEnumText, NULL),
        "created_at": (DateTime, NOT_NULL),
        "updated_at": (DateTime, NOT_NULL),
    },
    "staffing_gap": {
        "id": (BigInteger, NOT_NULL),
        "case_id": (BigInteger, NOT_NULL),
        "staffing_requirement_id": (BigInteger, NOT_NULL),
        "headcount_gap": (Integer, NOT_NULL),
        "computed_at": (DateTime, NOT_NULL),
    },
    "staffing_gap_role": {
        "gap_id": (BigInteger, NOT_NULL),
        "role_id": (BigInteger, NOT_NULL),
        "required_count": (Integer, NOT_NULL),
        "current_count": (Integer, NOT_NULL),
        "gap_count": (Integer, NOT_NULL),
    },
    "staffing_gap_skill": {
        "gap_id": (BigInteger, NOT_NULL),
        "skill_id": (BigInteger, NOT_NULL),
        "required_count": (Integer, NOT_NULL),
        "current_count": (Integer, NOT_NULL),
        "gap_count": (Integer, NOT_NULL),
    },
}

EXPECTED_PRIMARY_KEYS: dict[str, set[str]] = {
    "staff_skill": {"staff_id", "skill_id"},
    "staffing_requirement_role": {"staffing_requirement_id", "role_id"},
    "staffing_requirement_skill": {"staffing_requirement_id", "skill_id"},
    "staffing_gap_role": {"gap_id", "role_id"},
    "staffing_gap_skill": {"gap_id", "skill_id"},
}

# table -> column -> referenced column
EXPECTED_FOREIGN_KEYS: dict[str, dict[str, str]] = {
    "staff": {"role_id": "role.id", "home_ward_id": "ward.id"},
    "actors": {"staff_id": "staff.id"},
    "staff_skill": {"staff_id": "staff.id", "skill_id": "skill.id"},
    "shift": {"ward_id": "ward.id"},
    "staffing_events": {"shift_id": "shift.id", "staff_id": "staff.id"},
    "staffing_requirements": {"shift_id": "shift.id"},
    "staffing_requirement_role": {
        "staffing_requirement_id": "staffing_requirements.id",
        "role_id": "role.id",
    },
    "staffing_requirement_skill": {
        "staffing_requirement_id": "staffing_requirements.id",
        "skill_id": "skill.id",
    },
    "staffing_cases": {"event_id": "staffing_events.id", "shift_id": "shift.id"},
    "staff_unavailability": {"staff_id": "staff.id"},
    "roster_assignment": {"staff_id": "staff.id", "shift_id": "shift.id"},
    "staffing_gap": {
        "case_id": "staffing_cases.id",
        "staffing_requirement_id": "staffing_requirements.id",
    },
    "staffing_gap_role": {"gap_id": "staffing_gap.id", "role_id": "role.id"},
    "staffing_gap_skill": {"gap_id": "staffing_gap.id", "skill_id": "skill.id"},
}


def test_every_expected_table_is_registered() -> None:
    assert set(EXPECTED) <= set(Base.metadata.tables)


@pytest.mark.parametrize("table_name", sorted(EXPECTED))
def test_columns_match_the_schema_document(table_name: str) -> None:
    table = Base.metadata.tables[table_name]

    actual = {column.name: (type(column.type), column.nullable) for column in table.columns}

    assert actual == EXPECTED[table_name]


@pytest.mark.parametrize("table_name", sorted(EXPECTED))
def test_primary_key(table_name: str) -> None:
    table = Base.metadata.tables[table_name]

    assert {column.name for column in table.primary_key} == EXPECTED_PRIMARY_KEYS.get(
        table_name, {"id"}
    )


@pytest.mark.parametrize("table_name", sorted(EXPECTED))
def test_foreign_keys(table_name: str) -> None:
    table = Base.metadata.tables[table_name]

    actual = {fk.parent.name: fk.target_fullname for fk in table.foreign_keys}

    assert actual == EXPECTED_FOREIGN_KEYS.get(table_name, {})


@pytest.mark.parametrize("table_name", sorted(EXPECTED))
def test_timestamps_are_timezone_aware(table_name: str) -> None:
    table = Base.metadata.tables[table_name]

    naive = [c.name for c in table.columns if isinstance(c.type, DateTime) and not c.type.timezone]

    assert naive == []


@pytest.mark.parametrize("table_name", sorted(EXPECTED))
def test_ddl_compiles_for_postgresql(table_name: str) -> None:
    table = Base.metadata.tables[table_name]

    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))

    assert f"CREATE TABLE {table_name}" in ddl


def test_actor_constraints() -> None:
    table = Base.metadata.tables["actors"]
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    index = next(index for index in table.indexes if index.name == "uq_actors_name_non_user")
    index_ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "CONSTRAINT ck_actors_user_has_staff CHECK" in ddl
    assert "(actor_type = 'user') = (staff_id IS NOT NULL)" in ddl
    assert "CONSTRAINT uq_actors_staff_id UNIQUE (staff_id)" in ddl
    assert index_ddl == (
        "CREATE UNIQUE INDEX uq_actors_name_non_user ON actors (name) WHERE actor_type <> 'user'"
    )


def test_staffing_event_constraint() -> None:
    table = Base.metadata.tables["staffing_events"]

    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))

    assert "CONSTRAINT ck_staffing_events_staff_id_matches_event_group CHECK" in ddl
    assert (
        "(event_type IN ('ASSIGNMENT_CANCELLED', 'STAFF_UNAVAILABLE')) = (staff_id IS NOT NULL)"
        in ddl
    )
