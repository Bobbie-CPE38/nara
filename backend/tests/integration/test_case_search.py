"""GET /cases/search: the case list with search, filter and pages
(round 6 PR EV6, docs/workflow.md 6.36.6).

The seed: ICU night shift 1 and Medicine night shift 21. 900 is the ICU head nurse, 902 the
Medicine head nurse, 950 the Supervisor and 105 an ICU nurse.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import Shift
from app.domain.enums import CaseStatus
from app.main import app
from tests.integration import case_rows

ICU_NIGHT, MEDICINE_NIGHT = 1, 21
HEAD_NURSE, SUPERVISOR, NURSE = 900, 950, 105


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: seeded
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def cases(seeded: Session) -> list[int]:
    """Five ICU cases and two Medicine ones, in id order."""
    statuses = [
        CaseStatus.MANUAL_HANDOFF,
        CaseStatus.FAILED,
        CaseStatus.RESOLVED,
        CaseStatus.MANUAL_HANDOFF,
        CaseStatus.WAITING_RESPONSE,
    ]
    ids = [case_rows.make_case(seeded, status).id for status in statuses]
    ids += [
        case_rows.make_case(seeded, CaseStatus.MANUAL_HANDOFF, shift_id=MEDICINE_NIGHT).id,
        case_rows.make_case(seeded, CaseStatus.FAILED, shift_id=MEDICINE_NIGHT).id,
    ]
    return ids


def _search(client: TestClient, user: int = SUPERVISOR, **params: object) -> dict:
    response = client.get("/cases/search", params=params, headers={"X-Demo-User": str(user)})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_supervisor_pages_through_every_case_newest_first(
    client: TestClient, cases: list[int]
) -> None:
    first = _search(client, page_size=3)
    third = _search(client, page_size=3, page=3)

    assert first["total"] == 7 and first["page"] == 1 and first["page_size"] == 3
    assert [item["id"] for item in first["items"]] == cases[::-1][:3]
    assert [item["id"] for item in third["items"]] == [cases[0]]
    item = first["items"][0]
    assert (item["ward_name"], item["shift_type"]) == ("Medicine", "NIGHT")
    assert item["shift_start_at"].endswith("23:00:00+07:00")


def test_a_head_nurse_sees_her_ward_only(client: TestClient, cases: list[int]) -> None:
    body = _search(client, HEAD_NURSE)

    assert body["total"] == 5
    assert {item["ward_name"] for item in body["items"]} == {"ICU"}


def test_status_ward_and_sort_filters(client: TestClient, cases: list[int]) -> None:
    handoff = _search(client, status="MANUAL_HANDOFF,FAILED", sort="oldest")
    medicine = _search(client, ward_id=2)

    assert [item["id"] for item in handoff["items"]] == [
        cases[0],
        cases[1],
        cases[3],
        cases[5],
        cases[6],
    ]
    assert all(
        item["can_manage"] == (item["status"] == "MANUAL_HANDOFF") for item in handoff["items"]
    )
    assert [item["id"] for item in medicine["items"]] == [cases[6], cases[5]]


def test_the_search_matches_an_id_or_a_ward_name(client: TestClient, cases: list[int]) -> None:
    by_case = _search(client, q=str(cases[2]))
    by_shift = _search(client, q=str(MEDICINE_NIGHT))
    by_name = _search(client, q="medic")
    nothing = _search(client, q="50%_")

    assert [item["id"] for item in by_case["items"]] == [cases[2]]
    assert by_shift["total"] == 2
    assert by_name["total"] == 2
    assert nothing["total"] == 0 and nothing["items"] == []


def test_a_nurse_in_demo_mode_is_refused_like_the_handoff_list(
    client: TestClient, cases: list[int]
) -> None:
    refused = client.get("/cases/search", headers={"X-Demo-User": str(NURSE)})

    assert refused.status_code == 403


def test_bad_paging_is_a_422(client: TestClient) -> None:
    headers = {"X-Demo-User": str(SUPERVISOR)}

    assert client.get("/cases/search?page=0", headers=headers).status_code == 422
    assert client.get("/cases/search?page_size=101", headers=headers).status_code == 422
    assert client.get("/cases/search?sort=random", headers=headers).status_code == 422
    assert client.get("/cases/search?status=NOPE", headers=headers).status_code == 422


@pytest.mark.parametrize("digits", [19, 100])
def test_a_number_too_big_for_an_id_finds_nothing_instead_of_failing(
    client: TestClient, cases: list[int], digits: int
) -> None:
    """Review of #145: 100 nines made PostgreSQL fail with bigint out of range (500)."""
    body = _search(client, q="9" * digits)

    assert body["total"] == 0 and body["items"] == []


@pytest.mark.parametrize("sort", ["newest", "oldest"])
def test_exact_case_precedes_more_than_a_page_of_shift_matches(
    client: TestClient, seeded: Session, sort: str
) -> None:
    """#148: Manage must find its own row even with over 100 matches."""
    first = case_rows.make_case(seeded, CaseStatus.MANUAL_HANDOFF)
    # A different shift shares the case number; its cases are also search matches.
    if seeded.get(Shift, first.id) is None:
        template = seeded.get(Shift, ICU_NIGHT)
        assert template is not None
        seeded.add(
            Shift(
                id=first.id,
                ward_id=template.ward_id,
                patient_count=template.patient_count,
                start_at=template.start_at,
                end_at=template.end_at,
                shift_type=template.shift_type,
                is_active=True,
            )
        )
        seeded.flush()
    for _ in range(105):
        case_rows.make_case(seeded, CaseStatus.MANUAL_HANDOFF, shift_id=first.id)
    body = _search(client, q=str(first.id), page_size=100, sort=sort)
    assert body["total"] == 106
    assert len(body["items"]) == 100
    assert body["items"][0]["id"] == first.id
    assert body["items"][0]["can_manage"] is True
    other_ids = [row["id"] for row in body["items"][1:]]
    assert other_ids == sorted(other_ids, reverse=sort == "newest")
    # The exact match is still subject to status filters.
    first.status = CaseStatus.RESOLVED
    seeded.flush()
    filtered = _search(client, q=str(first.id), status="MANUAL_HANDOFF", page_size=100)
    assert filtered["total"] == 105
    assert first.id not in [row["id"] for row in filtered["items"]]
