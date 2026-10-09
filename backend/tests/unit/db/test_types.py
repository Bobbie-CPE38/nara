import pytest
from sqlalchemy.dialects import postgresql

from app.db.base import StrEnumText
from app.domain.enums import StaffStatus

DIALECT = postgresql.dialect()


def test_bind_writes_the_enum_value_as_text() -> None:
    column_type = StrEnumText(StaffStatus)

    assert column_type.process_bind_param(StaffStatus.ACTIVE, DIALECT) == "ACTIVE"


def test_bind_rejects_a_value_outside_the_enum() -> None:
    column_type = StrEnumText(StaffStatus)

    with pytest.raises(ValueError, match="ON_LEAVE"):
        column_type.process_bind_param("ON_LEAVE", DIALECT)  # type: ignore[arg-type]


def test_result_returns_the_enum_member() -> None:
    column_type = StrEnumText(StaffStatus)

    result = column_type.process_result_value("INACTIVE", DIALECT)

    assert result is StaffStatus.INACTIVE


def test_none_passes_through_both_ways() -> None:
    column_type = StrEnumText(StaffStatus)

    assert column_type.process_bind_param(None, DIALECT) is None
    assert column_type.process_result_value(None, DIALECT) is None


def test_database_type_is_plain_text() -> None:
    assert StrEnumText(StaffStatus).compile(dialect=DIALECT) == "TEXT"
