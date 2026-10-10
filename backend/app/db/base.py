from enum import StrEnum
from typing import Any, TypeVar

from sqlalchemy import Dialect, MetaData, Text, TypeDecorator
from sqlalchemy.orm import DeclarativeBase

# Deterministic constraint names so autogenerate diffs and hand-written
# constraints in migrations stay stable
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

E = TypeVar("E", bound=StrEnum)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class StrEnumText(TypeDecorator[E]):
    """Store a StrEnum as plain `text` (no DB ENUM / CHECK, see docs/database-schema.md)
    and load it back as the enum member."""

    impl = Text
    cache_ok = True

    def __init__(self, enum_cls: type[E], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.enum_cls = enum_cls

    def process_bind_param(self, value: E | None, dialect: Dialect) -> str | None:
        return None if value is None else self.enum_cls(value).value

    def process_result_value(self, value: str | None, dialect: Dialect) -> E | None:
        return None if value is None else self.enum_cls(value)
