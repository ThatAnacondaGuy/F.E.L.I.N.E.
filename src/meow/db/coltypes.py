"""Column types that keep SQLite honest about timezones and enums."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Dialect, String
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Stores UTC, returns aware datetimes, and refuses naive ones.

    SQLite has no timezone type; without this, aware datetimes silently lose their offset.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("naive datetime passed to the database; attach a timezone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


class StrEnumType[E: StrEnum](TypeDecorator[E]):
    """Stores a StrEnum as plain text so adding members never needs a migration."""

    impl = String(32)
    cache_ok = True

    def __init__(self, enum_cls: type[E], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.enum_cls = enum_cls

    def process_bind_param(self, value: E | str | None, dialect: Dialect) -> str | None:
        return None if value is None else self.enum_cls(value).value

    def process_result_value(self, value: str | None, dialect: Dialect) -> E | None:
        return None if value is None else self.enum_cls(value)
