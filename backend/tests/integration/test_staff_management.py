"""Real cookie permissions, bounded directory, and reuse of the signed LINK flow."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.dependencies import get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.models import Contact, LineAccountLinkCode, Staff
from app.domain.enums import StaffStatus
from app.main import app
from app.services import auth_service, line_account_service, line_webhook_service
from tests.integration import test_line_messaging
from tests.integration.test_line_account_linking import link_event, post

real_line = test_line_messaging.real_line

PASSWORD = "staff admin test password"


@pytest.fixture
def directory(production_seeded, monkeypatch):
    db = production_seeded
    monkeypatch.setattr(settings, "auth_mode", "session")
    for staff_id in (950, 900, 105):
        auth_service.create_account(db, staff_id, PASSWORD, must_change_password=False)
    limiter.clear()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": settings.cors_origins[0]}
    ) as client:
        yield client, db
    app.dependency_overrides.clear()
    limiter.clear()


def login(client, staff_id):
    response = client.post("/auth/login", json={"staff_id": staff_id, "password": PASSWORD})
    assert response.status_code == 200


@pytest.mark.parametrize("mode", ["demo", "session"])
@pytest.mark.parametrize("staff_id", [None, 105, 900])
def test_only_real_supervisor_session_can_read_or_issue(directory, monkeypatch, mode, staff_id):
    client, db = directory
    monkeypatch.setattr(settings, "auth_mode", mode)
    if staff_id is not None:
        login(client, staff_id)
    for method, path in [
        ("GET", "/admin/staff"),
        ("POST", "/admin/staff/201/line-code"),
        ("POST", "/admin/staff/201/line-unlink"),
    ]:
        response = client.request(method, path, headers={"X-Demo-User": "950"})
        assert response.status_code == (401 if staff_id is None else 403)
        assert response.headers["cache-control"] == "no-store"
    assert db.scalar(select(func.count()).select_from(LineAccountLinkCode)) == 0


def test_supervisor_search_pagination_and_minimal_fields(directory):
    client, db = directory
    login(client, 950)
    page = client.get("/admin/staff?limit=2&offset=2")
    assert page.status_code == 200
    ids = list(db.scalars(select(Staff.id).order_by(Staff.id)))
    assert page.json()["total"] == len(ids)
    assert [item["id"] for item in page.json()["items"]] == ids[2:4]
    found = client.get("/admin/staff?q=201").json()["items"]
    assert [item["id"] for item in found] == [201]
    assert set(found[0]) == {
        "id",
        "first_name",
        "last_name",
        "ward_name",
        "role",
        "status",
        "line_linked",
    }
    assert client.get("/admin/staff?q=%25").json()["total"] == 0
    assert client.get("/admin/staff?limit=101").status_code == 422
    assert client.get("/admin/staff?offset=-1").status_code == 422
    assert page.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("mode", ["demo", "session"])
def test_supervisor_issues_code_usable_by_existing_signed_link(
    directory, real_line, monkeypatch, mode
):
    client, db = directory
    monkeypatch.setattr(settings, "auth_mode", mode)
    login(client, 950)
    result = client.post("/admin/staff/201/line-code")
    assert result.status_code == 201
    assert result.headers["cache-control"] == "no-store"
    raw = result.json()["code"]
    stored = db.scalars(select(LineAccountLinkCode)).one()
    assert stored.code_hash == line_account_service.hash_code(raw)
    assert stored.code_hash != raw
    assert result.json()["expires_at"]
    assert post(client, link_event(raw)).status_code == 200
    assert db.scalar(select(Contact.staff_id).where(Contact.line_uid == "U201")) == 201
    assert client.get("/admin/staff?q=201").json()["items"][0]["line_linked"] is True
    assert client.post("/admin/staff/201/line-code").status_code == 409


@pytest.mark.parametrize("mode", ["demo", "session"])
def test_missing_origin_is_rejected_even_in_demo_mode(directory, monkeypatch, mode):
    client, db = directory
    monkeypatch.setattr(settings, "auth_mode", mode)
    login(client, 950)
    client.headers.pop("Origin")
    response = client.post("/admin/staff/201/line-code")
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert db.scalar(select(func.count()).select_from(LineAccountLinkCode)) == 0


def test_unavailable_staff_and_password_change(directory):
    client, db = directory
    login(client, 950)
    db.get(Staff, 201).status = StaffStatus.INACTIVE
    db.commit()
    for staff_id in (201, 999999):
        assert (
            client.post(f"/admin/staff/{staff_id}/line-code").json()["detail"]
            == "LINE_STAFF_UNAVAILABLE"
        )
    auth_service.reset_password(db, 950, "another password")
    client.cookies.clear()
    response = client.post("/auth/login", json={"staff_id": 950, "password": "another password"})
    assert response.status_code == 200
    assert client.get("/admin/staff").json()["detail"] == "AUTH_PASSWORD_CHANGE_REQUIRED"
    assert client.post("/admin/staff/202/line-code").status_code == 403
    assert db.scalar(select(func.count()).select_from(LineAccountLinkCode)) == 0


@pytest.mark.parametrize("command", ["MYID", "myid", "MYID\n"])
def test_myid_private_sender_only_and_redelivery(directory, real_line, command):
    client, db = directory
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.commit()
    item = link_event("unused")
    item["message"]["text"] = command
    for _ in range(2):
        assert post(client, item).status_code == 200
    real_line[1].assert_called_once_with("reply-test", "รหัสพนักงาน NARA ของคุณคือ 201")
    assert db.scalar(select(func.count()).select_from(LineAccountLinkCode)) == 0


@pytest.mark.parametrize("unavailable", ["unbound", "inactive_staff", "inactive_contact"])
def test_myid_unavailable_binding_does_not_disclose(directory, real_line, unavailable):
    client, db = directory
    if unavailable != "unbound":
        db.add(Contact(staff_id=201, line_uid="U201", is_active=unavailable != "inactive_contact"))
    if unavailable == "inactive_staff":
        db.get(Staff, 201).status = StaffStatus.INACTIVE
    db.commit()
    item = link_event("unused")
    item["message"]["text"] = "MYID"
    assert post(client, item).status_code == 200
    real_line[1].assert_called_once_with("reply-test", line_webhook_service._LINK_GUIDANCE)


@pytest.mark.parametrize("source_type", ["group", "room"])
def test_myid_never_discloses_in_shared_chat(directory, real_line, source_type):
    client, db = directory
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.commit()
    item = link_event("unused")
    item["source"]["type"] = source_type
    item["message"]["text"] = "MYID"
    assert post(client, item).status_code == 200
    real_line[1].assert_not_called()


def test_myid_cannot_choose_another_staff_id(directory, real_line):
    client, db = directory
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.commit()
    item = link_event("unused")
    item["message"]["text"] = "MYID 202"
    assert post(client, item).status_code == 200
    assert "202" not in real_line[1].call_args.args[1]


def test_code_issuance_is_bounded_per_supervisor(directory):
    client, db = directory
    login(client, 950)
    for _ in range(20):
        assert client.post("/admin/staff/201/line-code").status_code == 201
    response = client.post("/admin/staff/201/line-code")
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert response.headers["cache-control"] == "no-store"
    assert db.scalar(select(func.count()).select_from(LineAccountLinkCode)) == 20


@pytest.mark.parametrize("confirmation", [None, "", "202", 201, "0201", "201 "])
def test_unlink_requires_exact_typed_staff_id(directory, confirmation):
    client, db = directory
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.commit()
    login(client, 950)
    body = {} if confirmation is None else {"confirm_staff_id": confirmation}
    response = client.post("/admin/staff/201/line-unlink", json=body)
    assert response.status_code == (400 if confirmation == "202" else 422)
    assert response.headers["cache-control"] == "no-store"
    assert db.scalar(select(Contact.line_uid).where(Contact.staff_id == 201)) == "U201"


def test_unlink_revokes_proofs_preserves_account_and_audits_real_admin(directory, real_line):
    from app.db.models import AuditLog, AuthAccount, AuthRegistrationCode
    from app.domain.enums import AuditAction
    from app.services import actor_service, registration_service

    client, db = directory
    pending = line_account_service.issue_code(db, 201)
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.commit()
    registration_service.issue(db, "U201")
    db.commit()
    auth_service.create_account(db, 201, PASSWORD, must_change_password=False)
    # Inactive staff can still have their binding removed.
    db.get(Staff, 201).status = StaffStatus.INACTIVE
    db.commit()
    login(client, 950)
    response = client.post("/admin/staff/201/line-unlink", json={"confirm_staff_id": "201"})
    assert response.status_code == 200
    assert response.json() == {"unlinked_contacts": 1}
    assert response.headers["cache-control"] == "no-store"
    assert db.scalar(select(Contact.line_uid).where(Contact.staff_id == 201)) is None
    assert db.scalars(select(LineAccountLinkCode)).one().revoked_at is not None
    assert db.scalars(select(AuthRegistrationCode)).one().revoked_at is not None
    subject = db.get(Staff, 201).auth_subject
    assert db.get(AuthAccount, subject) is not None
    audit = db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.LINE_ACCOUNT_UNLINKED)
    ).one()
    assert audit.actor_id == actor_service.user_id(db, 950)
    assert "U201" not in str(audit.payload)
    assert pending.code.get_secret_value() not in str(audit.payload)
    assert client.get("/admin/staff?q=201").json()["items"][0]["line_linked"] is False
    assert client.post("/admin/staff/201/line-unlink", json={"confirm_staff_id": "201"}).json() == {
        "unlinked_contacts": 0
    }
    item = link_event("unused")
    item["message"]["text"] = "MYID"
    assert post(client, item).status_code == 200
    real_line[1].assert_called_once_with("reply-test", line_webhook_service._LINK_GUIDANCE)


@pytest.mark.parametrize("mode", ["demo", "session"])
def test_unlink_rejects_foreign_origin_before_writing(directory, monkeypatch, mode):
    client, db = directory
    monkeypatch.setattr(settings, "auth_mode", mode)
    db.add(Contact(staff_id=201, line_uid="U201", is_active=True))
    db.commit()
    login(client, 950)
    response = client.post(
        "/admin/staff/201/line-unlink",
        json={"confirm_staff_id": "201"},
        headers={"Origin": "https://untrusted.example"},
    )
    assert response.status_code == 403
    assert db.scalar(select(Contact.line_uid).where(Contact.staff_id == 201)) == "U201"
