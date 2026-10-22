"""AU5 one migration head, safe upgrade/downgrade and database code constraints."""

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import AuthAccount, AuthRegistrationCode, Contact
from app.seed.reset import ALEMBIC_INI
from app.services import auth_service, registration_service

REVISION = "b8f3d5a0c2e4"


def test_au5_has_one_head_after_au1():
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1
    assert REVISION in {row.revision for row in script.iterate_revisions("heads", "base")}
    assert script.get_revision(REVISION).down_revision == "a7e2c4f9b1d3"


def test_downgrade_only_removes_registration_proofs(production_seeded):
    db = production_seeded
    auth_service.create_account(db, 201, "a sufficiently long password")
    subject = db.scalar(select(AuthAccount.staff_subject))
    module = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION).module
    with Operations.context(MigrationContext.configure(db.connection())):
        module.downgrade()
        assert "auth_registration_code" not in inspect(db.connection()).get_table_names()
        assert db.get(AuthAccount, subject) is not None
        module.upgrade()
    assert db.scalar(select(func.count()).select_from(AuthRegistrationCode)) == 0


@pytest.mark.parametrize(
    "column,value",
    [
        ("code_hash", "bad"),
        ("code_hash", "F" * 64),
        ("line_uid_hash", "bad"),
        ("expires_at", "2000-01-01T00:00:00+00:00"),
    ],
)
def test_database_rejects_invalid_code_storage(production_seeded, column, value):
    db = production_seeded
    registration_service.issue_limiter.clear()
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.commit()
    registration_service.issue(db, "U201")
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(text(f"UPDATE auth_registration_code SET {column} = :value"), {"value": value})
