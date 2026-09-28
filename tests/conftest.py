from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from meow.config import Profile, Settings, load_profile
from meow.db.engine import make_engine, make_session_factory, upgrade


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No test may touch the real data directory or the Keychain."""
    monkeypatch.setenv("MEOW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MEOW_API_TOKEN", "test-token")


@pytest.fixture
def profile() -> Profile:
    return load_profile()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(home=tmp_path / "home")


@pytest.fixture
def db(settings: Settings) -> Iterator[Session]:
    settings.ensure_home()
    engine = make_engine(settings.db_path)
    upgrade(engine)
    with make_session_factory(engine)() as session:
        yield session
    engine.dispose()
