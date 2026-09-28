"""Alembic environment. Run through ``meow db upgrade``; there is no alembic.ini."""

from __future__ import annotations

from typing import Any, Literal

from alembic import context
from sqlalchemy import Connection, create_engine

from meow.db.coltypes import StrEnumType, UTCDateTime
from meow.db.models import Base

config = context.config
target_metadata = Base.metadata


def _render_item(type_: str, obj: Any, autogen_context: Any) -> str | Literal[False]:
    """Write app-specific column types as plain SQL types so migrations stand alone."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime()"
    if type_ == "type" and isinstance(obj, StrEnumType):
        return "sa.String(length=32)"
    return False


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite needs table rebuilds for most ALTERs
        compare_type=True,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(config.get_main_option("sqlalchemy.url") or "")
    with engine.connect() as conn:
        _run(conn)


if context.is_offline_mode():
    raise SystemExit("Offline migrations are not supported.")
run_migrations_online()
