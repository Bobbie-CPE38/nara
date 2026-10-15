"""Shared authority for approvals and handoff; staff membership remains separate."""

import pytest

from app.domain.staffing.ward_authority import can_decide, manages_ward


@pytest.mark.parametrize(
    "role,home,ward,waited,expected",
    [
        ("HEAD_NURSE", 1, 1, False, True),
        ("HEAD_NURSE", 1, 2, True, False),
        ("SUPERVISOR", 1, 2, False, False),
        ("SUPERVISOR", 1, 2, True, True),
        ("SUPERVISOR", None, 2, True, True),
        ("RN", 1, 1, True, False),
        (None, 1, 1, True, False),
        ("HEAD_NURSE", None, 1, True, False),
    ],
)
def test_actor_authority(role, home, ward, waited, expected):
    assert can_decide(role=role, home_ward_id=home, ward_id=ward, waited=waited) is expected


def test_supervisor_authority_does_not_change_staff_membership():
    assert not manages_ward(home_ward_id=1, ward_id=2)


def test_a_head_nurse_manages_their_own_ward() -> None:
    assert manages_ward(home_ward_id=1, ward_id=1) is True


def test_a_head_nurse_does_not_manage_another_ward() -> None:
    assert manages_ward(home_ward_id=2, ward_id=1) is False
    assert manages_ward(home_ward_id=1, ward_id=2) is False
