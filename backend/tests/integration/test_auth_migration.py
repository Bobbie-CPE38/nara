"""Round 6 PR AU1 migration: subjects for existing staff, no usable password, one head."""

import uuid
from types import ModuleType

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AuthAccount, Staff
from app.seed.reset import ALEMBIC_INI
from app.services import auth_service

REVISION = "a7e2c4f9b1d3"
INSERT_SESSION = text(
    "INSERT INTO auth_session (account_subject, token_hash, credential_version,"
    " created_at, last_seen_at, expires_at)"
    " VALUES (:subject, :token_hash, 1, now(), now(), now() + CAST(:lifetime AS interval))"
)


def _migration() -> ModuleType:
    revision = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION)
    assert revision is not None
    return revision.module


def _subject_with_account(db: Session, staff_id: int) -> uuid.UUID:
    auth_service.create_account(db, staff_id, "a long enough password")
    return db.scalars(select(Staff.auth_subject).where(Staff.id == staff_id)).one()


def test_one_head_after_au1() -> None:
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))

    assert script.get_heads() == [REVISION]
    assert script.get_revision(REVISION).down_revision == "f9a1c3e5b7d2"  # type: ignore[union-attr]


def test_upgrade_gives_existing_staff_distinct_subjects_and_no_account(
    production_seeded: Session,
) -> None:
    db = production_seeded
    staff_count = db.scalar(select(func.count()).select_from(Staff))
    with Operations.context(MigrationContext.configure(db.connection())):
        _migration().downgrade()
        columns = {c["name"] for c in inspect(db.connection()).get_columns("staff")}
        assert "auth_subject" not in columns
        assert "auth_account" not in inspect(db.connection()).get_table_names()
        _migration().upgrade()

    subjects = db.execute(text("SELECT auth_subject FROM staff")).scalars().all()
    assert len(subjects) == staff_count == len(set(subjects))
    assert all(isinstance(subject, uuid.UUID) and subject.version == 4 for subject in subjects)
    # The seed's "!" in STAFF.password_hash does not become a password
    assert db.scalar(select(func.count()).select_from(AuthAccount)) == 0


def test_subject_cannot_change(production_seeded: Session) -> None:
    db = production_seeded
    db.execute(text("UPDATE staff SET first_name = 'Renamed' WHERE id = 105"))
    with pytest.raises(DBAPIError, match="auth_subject cannot change"):
        db.execute(text("UPDATE staff SET auth_subject = gen_random_uuid() WHERE id = 105"))


def test_staff_with_an_account_cannot_be_deleted(production_seeded: Session) -> None:
    db = production_seeded
    _subject_with_account(db, 201)
    for table in ("actors", "staff_skill", "roster_assignment"):
        db.execute(text(f"DELETE FROM {table} WHERE staff_id = 201"))
    with pytest.raises(IntegrityError, match="fk_auth_account_staff_subject_staff"):
        db.execute(text("DELETE FROM staff WHERE id = 201"))


@pytest.mark.parametrize("token_hash", ["abc", "F" * 64, "g" * 64])
def test_session_stores_only_a_lowercase_sha256(
    production_seeded: Session, token_hash: str
) -> None:
    db = production_seeded
    subject = _subject_with_account(db, 201)
    with pytest.raises(IntegrityError, match="token_hash_sha256_hex"):
        db.execute(
            INSERT_SESSION,
            {"subject": subject, "token_hash": token_hash, "lifetime": "1 hour"},
        )


def test_session_times_are_ordered(production_seeded: Session) -> None:
    db = production_seeded
    subject = _subject_with_account(db, 201)
    with pytest.raises(IntegrityError, match="time_order"):
        db.execute(INSERT_SESSION, {"subject": subject, "token_hash": "a" * 64, "lifetime": "0"})
