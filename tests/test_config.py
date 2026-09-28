from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from meow.config import Settings, load_profile
from meow.types import AuthorityLevel, BlockKind, CoursePriority, ProposalKind


def test_defaults_describe_aniket() -> None:
    profile = load_profile()
    assert profile.user.timezone == "Asia/Kolkata"
    assert profile.course("PCC301COM").priority is CoursePriority.HIGHEST
    assert {b.kind for b in profile.schedule} == set(BlockKind)
    assert profile.autonomy.kinds[ProposalKind.CREATE_TASK].level is AuthorityLevel.L2


def test_user_file_overrides_tables_and_replaces_arrays(tmp_path: Path) -> None:
    user = tmp_path / "config.toml"
    user.write_text(
        '[planner]\nmax_focus_hours_per_day = 4\n\n[[courses]]\ncode = "X1"\nname = "Only course"\n'
    )
    profile = load_profile(user)
    assert profile.planner.max_focus_hours_per_day == 4
    assert profile.planner.horizon_days == 7  # untouched keys survive
    assert [c.code for c in profile.courses] == ["X1"]


@pytest.mark.parametrize(
    ("toml", "message"),
    [
        ("[scoring.weights]\nurgency = 0.9\n", "sum to 1.0"),
        ('[user]\ntimezone = "Mars/Olympus"\n', "unknown timezone"),
        ("[planner]\nmin_session_minutes = 200\n", "min_session_minutes"),
        ('[autonomy.kinds.create_task]\nlevel = "L1"\nmost_autonomous = "L2"\n', "more autonomous"),
    ],
)
def test_invalid_config_is_rejected_loudly(tmp_path: Path, toml: str, message: str) -> None:
    user = tmp_path / "config.toml"
    user.write_text(toml)
    with pytest.raises(ValidationError, match=message):
        load_profile(user)


def test_settings_honour_meow_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEOW_HOME", str(tmp_path / "elsewhere"))
    assert Settings().db_path == tmp_path / "elsewhere" / "meow.db"
