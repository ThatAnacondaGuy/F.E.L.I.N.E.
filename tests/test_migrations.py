"""The schema drift that crashed the old prototype (models and SQL disagreeing) fails here."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from meow.config import Settings
from meow.db.engine import current_revision, head_revision, make_engine, upgrade
from meow.db.models import Base, Task

from support import ist


def test_migrations_build_exactly_the_models(settings: Settings) -> None:
    settings.ensure_home()
    engine = make_engine(settings.db_path)
    upgrade(engine)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == [], f"models and migrations disagree: {diff}"


def test_upgrade_is_idempotent_and_reaches_head(settings: Settings) -> None:
    settings.ensure_home()
    engine = make_engine(settings.db_path)
    upgrade(engine)
    upgrade(engine)
    assert current_revision(engine) == head_revision()
    assert {"tasks", "proposals", "audit_log"} <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_datetimes_round_trip_as_aware_utc(db: Session) -> None:
    due = ist(2026, 10, 2, 23, 59)
    db.add(Task(title="t", due_at=due))
    db.commit()
    db.expire_all()
    stored = db.query(Task).one().due_at
    assert stored == due and stored is not None and stored.tzinfo is UTC
    raw = db.execute(text("SELECT due_at FROM tasks")).scalar_one()
    assert str(raw).startswith("2026-10-02 18:29")  # stored as UTC


def test_naive_datetimes_never_reach_the_database(db: Session) -> None:
    db.add(Task(title="t", due_at=datetime(2026, 10, 2, 23, 59)))  # noqa: DTZ001
    with pytest.raises(Exception, match="naive datetime"):
        db.commit()


def test_foreign_keys_are_enforced(db: Session) -> None:
    db.add(Task(title="t", proposal_id="does-not-exist"))
    with pytest.raises(Exception, match="FOREIGN KEY"):
        db.commit()
