"""Writer validation must check effective endpoints, including mixed NULLs."""

from datetime import timedelta

import pytest

from app.services.roster_time_service import effective_interval
from tests.unit.domain.test_hard_rules import MONDAY


@pytest.mark.parametrize(("start", "end"), [(8, None), (9, None), (None, 0), (None, -1)])
def test_rejects_mixed_nulls_that_invert_or_empty_the_effective_interval(start, end):
    with pytest.raises(ValueError, match="effective roster interval"):
        effective_interval(
            shift_start_at=MONDAY,
            shift_end_at=MONDAY + timedelta(hours=8),
            actual_start_at=None if start is None else MONDAY + timedelta(hours=start),
            actual_end_at=None if end is None else MONDAY + timedelta(hours=end),
        )


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (None, None, (0, 8)),
        (2, None, (2, 8)),
        (None, 2, (0, 2)),
        (2, 6, (2, 6)),
    ],
)
def test_validates_each_endpoint_fallback_independently(start, end, expected):
    assert effective_interval(
        shift_start_at=MONDAY,
        shift_end_at=MONDAY + timedelta(hours=8),
        actual_start_at=None if start is None else MONDAY + timedelta(hours=start),
        actual_end_at=None if end is None else MONDAY + timedelta(hours=end),
    ) == tuple(MONDAY + timedelta(hours=offset) for offset in expected)
