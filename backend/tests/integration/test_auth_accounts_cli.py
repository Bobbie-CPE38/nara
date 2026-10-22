"""python -m app.auth_accounts (docs/workflow.md 6.33.2, round 6 PR AU1)."""

import io
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth_accounts
from app.core import passwords
from app.core.config import settings
from app.db.models import AuthAccount, AuthSession, Staff
from app.services import auth_service

PASSWORD = "  spaces count too  "


@pytest.fixture
def db(production_seeded: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    @contextmanager
    def same_session() -> Iterator[Session]:
        yield production_seeded

    monkeypatch.setattr(auth_accounts, "SessionLocal", same_session)
    return production_seeded


def run(monkeypatch: pytest.MonkeyPatch, *argv: str, stdin: str = PASSWORD + "\n") -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    auth_accounts.main([*argv, "--password-stdin"])


def account(db: Session, staff_id: int) -> AuthAccount | None:
    db.expire_all()
    return db.scalar(
        select(AuthAccount)
        .join(Staff, Staff.auth_subject == AuthAccount.staff_subject)
        .where(Staff.id == staff_id)
    )


def live_sessions(db: Session) -> int | None:
    return db.scalar(
        select(func.count()).select_from(AuthSession).where(AuthSession.revoked_at.is_(None))
    )


def test_create_sets_a_temporary_password_read_exactly_from_stdin(
    db: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run(monkeypatch, "create", "--staff-id", "105")

    created = account(db, 105)
    assert created is not None and created.must_change_password
    assert passwords.verify_password(created.password_hash, PASSWORD)
    assert not passwords.verify_password(created.password_hash, PASSWORD.strip())
    out = capsys.readouterr()
    assert PASSWORD.strip() not in out.out + out.err
    assert created.password_hash not in out.out + out.err


def test_password_is_never_an_argument(db: Session) -> None:
    with pytest.raises(SystemExit):
        auth_accounts.main(["create", "--staff-id", "105", "--password", PASSWORD])
    assert account(db, 105) is None


def test_getpass_must_match(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(["first try password", "second try password"])
    monkeypatch.setattr(auth_accounts.getpass, "getpass", lambda prompt: next(answers))

    with pytest.raises(SystemExit, match="do not match"):
        auth_accounts.main(["create", "--staff-id", "105"])
    assert account(db, 105) is None


@pytest.mark.parametrize("password", ["too short", "x" * 129, ""])
def test_unacceptable_password_changes_nothing(
    db: Session, monkeypatch: pytest.MonkeyPatch, password: str
) -> None:
    with pytest.raises(SystemExit, match="12 to 128"):
        run(monkeypatch, "create", "--staff-id", "105", stdin=password + "\n")
    assert account(db, 105) is None


def test_create_twice_or_for_unknown_staff_is_refused(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run(monkeypatch, "create", "--staff-id", "105")
    with pytest.raises(SystemExit, match="already has an account"):
        run(monkeypatch, "create", "--staff-id", "105")
    with pytest.raises(SystemExit, match="does not exist"):
        run(monkeypatch, "create", "--staff-id", "999999")


def test_reset_password_ends_every_session_and_forces_a_change(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_service.create_account(db, 105, "the first password", must_change_password=False)
    assert auth_service.login(db, 105, "the first password") is not None
    assert live_sessions(db) == 1

    run(monkeypatch, "reset-password", "--staff-id", "105")

    reset = account(db, 105)
    assert reset is not None
    assert (reset.credential_version, reset.must_change_password) == (2, True)
    assert live_sessions(db) == 0
    assert auth_service.login(db, 105, "the first password") is None
    assert auth_service.login(db, 105, PASSWORD) is not None


def test_disable_ends_sessions_and_blocks_login_until_enabled(db: Session) -> None:
    auth_service.create_account(db, 105, PASSWORD, must_change_password=False)
    result = auth_service.login(db, 105, PASSWORD)
    assert result is not None
    token = result[0]

    auth_accounts.main(["disable", "--staff-id", "105"])

    assert live_sessions(db) == 0
    assert auth_service.resolve(db, token) is None
    assert auth_service.login(db, 105, PASSWORD) is None
    auth_accounts.main(["enable", "--staff-id", "105"])
    assert auth_service.login(db, 105, PASSWORD) is not None
    # The session that disable ended stays ended
    assert auth_service.resolve(db, token) is None


def test_demo_accounts_only_in_local_demo_mode(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in (("auth_mode", "session"), ("app_env", "aws")):
        with monkeypatch.context() as patch:
            patch.setattr(settings, name, value)
            with pytest.raises(SystemExit, match="only with AUTH_MODE=demo"):
                run(monkeypatch, "demo-accounts")
    assert db.scalar(select(func.count()).select_from(AuthAccount)) == 0

    run(monkeypatch, "demo-accounts")

    assert db.scalar(select(func.count()).select_from(AuthAccount)) == len(
        auth_accounts.demo_staff_ids()
    )
    head_nurse = account(db, 900)
    assert head_nurse is not None and head_nurse.must_change_password is False
    # Again: nobody is overwritten
    run(monkeypatch, "demo-accounts", stdin="another demo password\n")
    assert auth_service.login(db, 900, PASSWORD) is not None
