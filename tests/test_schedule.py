from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from meow.config import Profile
from meow.domain.schedule import WeeklySchedule
from meow.types import BlockKind

from support import IST, ist


@pytest.fixture
def week(profile: Profile) -> WeeklySchedule:
    return WeeklySchedule(profile.schedule, IST)


def test_weekday_focus_runs_past_midnight(week: WeeklySchedule) -> None:
    windows = week.focus_windows(ist(2026, 9, 28), ist(2026, 9, 29, 12))
    monday = next(w for w in windows if w.day.day == 28)
    assert monday.interval.start == ist(2026, 9, 28, 16, 30)
    assert monday.interval.end == ist(2026, 9, 29, 4, 0)


def test_last_nights_block_is_found_in_the_small_hours(week: WeeklySchedule) -> None:
    # 01:00 Monday belongs to Sunday's weekend block.
    block = week.block_at(ist(2026, 9, 28, 1, 0))
    assert block is not None and block.name == "Weekend"


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (ist(2026, 9, 28, 5, 0), BlockKind.SLEEP),
        (ist(2026, 9, 28, 8, 30), BlockKind.ROUTINE),
        (ist(2026, 9, 28, 11, 0), BlockKind.COLLEGE),
        (ist(2026, 9, 28, 16, 30), BlockKind.FOCUS),
        (ist(2026, 10, 3, 8, 30), BlockKind.FOCUS),  # Saturday: open from 08:00
    ],
)
def test_block_at(week: WeeklySchedule, moment: datetime, expected: BlockKind) -> None:
    block = week.block_at(moment)
    assert block is not None and block.kind is expected


def test_quiet_hours_are_exactly_four_to_eight(week: WeeklySchedule) -> None:
    assert not week.is_quiet(ist(2026, 9, 28, 3, 59))
    assert week.is_quiet(ist(2026, 9, 28, 4, 0))
    assert week.is_quiet(ist(2026, 9, 28, 7, 59))
    assert not week.is_quiet(ist(2026, 9, 28, 8, 0))


def test_default_schedule_has_no_overlaps_and_sane_capacity(week: WeeklySchedule) -> None:
    assert week.overlaps() == []
    # 5 weekdays x 11.5h + 2 weekend days x 20h
    assert week.weekly_focus_hours() == pytest.approx(5 * 11.5 + 2 * 20)


def test_next_sleep_after_evening_is_four_am(week: WeeklySchedule) -> None:
    now = ist(2026, 9, 28, 20, 0)
    assert week.next_start(BlockKind.SLEEP, now) == ist(2026, 9, 29, 4, 0)
    assert week.next_start(BlockKind.SLEEP, now + timedelta(hours=7)) == ist(2026, 9, 29, 4, 0)
