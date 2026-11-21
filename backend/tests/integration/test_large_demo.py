"""Large demo: additive import, no outbound work, collision refusal and auth-safe replay."""

import json
from contextlib import contextmanager

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import settings
from app.db.models import (
    AuthAccount,
    AuthSession,
    CandidateOutreach,
    Contact,
    DemoDataset,
    LlmCallLog,
    RosterAssignment,
    Skill,
    Staff,
    StaffingCase,
    StaffingGapSkill,
    StructuredHandover,
    Ward,
)
from app.db.session import SessionLocal
from app.domain.enums import CaseStatus, RosterStatus
from app.seed.large_demo import PROFILE, STAFF_BASE, WARD_BASE, counts, generate
from app.seed.reset import reset_demo
from app.services import auth_service, case_service, job_service


def test_large_import_is_additive_idempotent_and_does_not_queue_paid_or_live_work(
    production_seeded: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "line_mode", "real")
    monkeypatch.setattr(settings, "line_channel_secret", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "line_channel_access_token", SecretStr("test-token"))
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "bedrock")
    monkeypatch.setattr(settings, "llm_model_id", "test-model")
    monkeypatch.setattr(settings, "aws_region", "ap-southeast-1")
    db = production_seeded
    original = db.scalars(select(Staff).where(Staff.id == 900)).one()
    subject = original.auth_subject
    db.add(Contact(staff_id=201, line_uid="U-existing-binding", is_active=True))
    db.flush()
    before_subjects = dict(db.execute(select(Staff.id, Staff.auth_subject)).all())
    auth_service.hold_auth_gate(db)
    result = generate(db, clock.now())
    assert result == {"staff": 500, "wards": 20, "shifts": 1200}
    assert generate(db, clock.now()) == result
    assert db.scalar(select(func.count()).select_from(DemoDataset)) == 1
    assert db.scalar(select(func.count()).select_from(Staff)) == len(before_subjects) + 500
    for staff_id, kept in before_subjects.items():
        assert db.get(Staff, staff_id).auth_subject == kept
    assert db.get(Staff, 900).auth_subject == subject
    assert (
        db.scalar(select(Contact.line_uid).where(Contact.staff_id == 201)) == "U-existing-binding"
    )
    assert db.scalar(select(func.count()).select_from(AuthAccount)) == 0
    assert db.scalar(select(func.count()).select_from(CandidateOutreach)) == 0
    assert db.scalar(select(func.count()).select_from(LlmCallLog)) == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(StructuredHandover)
            .where(StructuredHandover.delivery_status.is_not(None))
        )
        == 0
    )
    job_service.run_due_work(db)
    assert db.scalar(select(func.count()).select_from(CandidateOutreach)) == 0
    assert db.scalar(select(func.count()).select_from(LlmCallLog)) == 0
    cancelled = db.scalars(
        select(RosterAssignment).where(
            RosterAssignment.staff_id.between(STAFF_BASE + 1, STAFF_BASE + 24),
            RosterAssignment.status == RosterStatus.CANCELLED,
        )
    ).all()
    assert len({(row.staff_id - STAFF_BASE - 1) // 6 for row in cancelled}) == 4
    assert len({(row.staff_id - STAFF_BASE - 1) % 6 for row in cancelled}) > 1
    for skill_name in ("ICU", "BLS"):
        assert (
            db.scalar(
                select(func.count())
                .select_from(StaffingGapSkill)
                .join(Skill, Skill.id == StaffingGapSkill.skill_id)
                .where(Skill.name == skill_name, StaffingGapSkill.gap_count > 0)
            )
            > 0
        )
    # Every historical status renders through the real read model.
    for status in (CaseStatus.RESOLVED, CaseStatus.UNRESOLVED, CaseStatus.FAILED):
        case_id = db.scalar(select(StaffingCase.id).where(StaffingCase.status == status).limit(1))
        assert case_id is not None
        detail = case_service.get_case_detail(db, case_id)
        assert detail.status == status
        if status == CaseStatus.RESOLVED:
            assert detail.assigned_count >= 1
            assert detail.handovers


def test_occupied_namespace_refuses_before_adding_people(production_seeded: Session) -> None:
    db = production_seeded
    db.add(Ward(id=WARD_BASE + 1, name="An existing unrelated ward", is_active=True))
    db.flush()
    with pytest.raises(ValueError, match="namespace is occupied"):
        generate(db, clock.now())
    assert counts(db)["staff"] == 0
    assert db.scalar(select(func.count()).select_from(DemoDataset)) == 0


@pytest.mark.usefixtures("restore_empty_database")
def test_reset_replays_large_profile_preserving_old_and_new_accounts_and_subjects() -> None:
    reset_demo()
    with SessionLocal() as db:
        auth_service.hold_auth_gate(db)
        generate(db, clock.now())
        db.commit()
        for staff_id in (900, STAFF_BASE + 1):
            auth_service.create_account(
                db, staff_id, "a private test password", must_change_password=False
            )
        login = auth_service.login(db, STAFF_BASE + 1, "a private test password")
        assert login is not None
        token = login[0]
        subjects = dict(db.execute(select(Staff.id, Staff.auth_subject)).all())
        passwords = dict(
            db.execute(select(AuthAccount.staff_subject, AuthAccount.password_hash)).all()
        )
    reset_demo()
    with SessionLocal() as db:
        assert counts(db) == {"staff": 500, "wards": 20, "shifts": 1200}
        assert dict(db.execute(select(Staff.id, Staff.auth_subject)).all()) == subjects
        assert (
            dict(db.execute(select(AuthAccount.staff_subject, AuthAccount.password_hash)).all())
            == passwords
        )
        # Round 6 PR EV6 (6.36.2): the login survives the reset too
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 1
        kept = auth_service.resolve(db, token)
        assert kept is not None and kept.staff.id == STAFF_BASE + 1
        db.rollback()
        assert db.scalars(select(DemoDataset.profile)).one() == PROFILE
        assert db.scalar(select(func.count()).select_from(RosterAssignment)) > 7200
        assert auth_service.login(db, STAFF_BASE + 1, "a private test password") is not None


@pytest.mark.usefixtures("restore_empty_database")
def test_unknown_profile_refuses_reset_without_losing_existing_accounts() -> None:
    from app.seed.reset import IdentityConflictError

    reset_demo()
    with SessionLocal() as db:
        auth_service.create_account(
            db, 900, "another private test password", must_change_password=False
        )
        db.add(DemoDataset(profile="unsupported-future-profile", reference_at=clock.now()))
        db.commit()
        subject = db.get(Staff, 900).auth_subject
    with pytest.raises(IdentityConflictError, match="Unknown demo dataset"):
        reset_demo()
    with SessionLocal() as db:
        assert db.get(Staff, 900).auth_subject == subject
        assert db.get(AuthAccount, subject) is not None
        assert db.scalars(select(DemoDataset.profile)).one() == "unsupported-future-profile"


def test_cli_clock_failure_is_clear_and_does_not_write(
    production_seeded: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app import mock_data

    @contextmanager
    def session():
        yield production_seeded

    def unavailable():
        raise ValueError("Cannot read a valid local Backend /clock. No dataset was written.")

    monkeypatch.setattr(mock_data, "SessionLocal", session)
    monkeypatch.setattr(mock_data, "backend_reference", unavailable)
    monkeypatch.setattr("sys.argv", ["mock_data", "--apply"])
    with pytest.raises(SystemExit) as stopped:
        mock_data.main()
    assert stopped.value.code == 1
    stderr = capsys.readouterr().err
    assert "Import refused:" in stderr and "Traceback" not in stderr
    assert counts(production_seeded) == {"staff": 0, "wards": 0, "shifts": 0}
    assert production_seeded.scalar(select(func.count()).select_from(DemoDataset)) == 0


def test_cli_reapply_uses_recorded_reference_without_clock(
    production_seeded: Session, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app import mock_data

    db = production_seeded
    generate(db, clock.now())
    reference = db.scalars(select(DemoDataset.reference_at)).one()

    @contextmanager
    def session():
        yield db

    def unexpected_clock():
        pytest.fail("An existing dataset must use its recorded reference, without HTTP")

    monkeypatch.setattr(mock_data, "SessionLocal", session)
    monkeypatch.setattr(db, "commit", lambda: db.flush())
    monkeypatch.setattr(mock_data, "backend_reference", unexpected_clock)
    monkeypatch.setattr("sys.argv", ["mock_data", "--apply"])
    mock_data.main()
    preview, loaded = map(json.loads, capsys.readouterr().out.splitlines())
    assert preview["reference_at"] == reference.isoformat()
    assert preview["already_loaded"] is True
    assert loaded["loaded"] == {"staff": 500, "wards": 20, "shifts": 1200}
