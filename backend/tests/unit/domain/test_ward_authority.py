from app.domain.staffing.ward_authority import manages_ward


def test_a_head_nurse_manages_their_own_ward() -> None:
    assert manages_ward(home_ward_id=1, ward_id=1) is True


def test_a_head_nurse_does_not_manage_another_ward() -> None:
    assert manages_ward(home_ward_id=2, ward_id=1) is False
    assert manages_ward(home_ward_id=1, ward_id=2) is False
