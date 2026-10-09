from enum import StrEnum
from typing import Any, TypeVar

from sqlalchemy import Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

E = TypeVar("E", bound=StrEnum)


class StrEnumText(TypeDecorator[E]):
    """A StrEnum stored as plain `text` (docs/database-schema.md: no DB ENUM, no CHECK).

    Python gets the enum member back on read, and a value outside the enum
    raises ValueError on write instead of reaching the database.
    """

    impl = Text
    cache_ok = True

    def __init__(self, enum_class: type[E]) -> None:
        super().__init__()
        self.enum_class = enum_class

    def process_bind_param(self, value: E | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return self.enum_class(value).value

    def process_result_value(self, value: Any | None, dialect: Dialect) -> E | None:
        if value is None:
            return None
        return self.enum_class(value)
