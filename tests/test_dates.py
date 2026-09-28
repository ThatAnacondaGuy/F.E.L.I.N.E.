from __future__ import annotations

from datetime import date, time

import pytest

from meow.domain.dates import read_time, resolve

MONDAY = date(2026, 9, 28)


@pytest.mark.parametrize(
    ("phrase", "day", "clock"),
    [
        # The two phrases qwen3 got wrong in the real-model probe:
        ("by this Friday, 5 PM", date(2026, 10, 2), time(17, 0)),
        ("Unit test 1 on Thursday during the lecture", date(2026, 10, 1), None),
        # and the rest of the everyday vocabulary
        ("next Monday before 11:59 PM", date(2026, 10, 5), time(23, 59)),
        ("Monday", date(2026, 10, 5), None),  # naming today's weekday means next week
        ("by tomorrow noon", date(2026, 9, 29), time(12, 0)),
        ("tonight", MONDAY, None),
        ("day after tomorrow, 9am", date(2026, 9, 30), time(9, 0)),
        ("by 3 October, 11:59 PM IST", date(2026, 10, 3), time(23, 59)),
        ("on 3rd Oct", date(2026, 10, 3), None),
        ("October 15, 2026 at 17:30", date(2026, 10, 15), time(17, 30)),
        ("before 05/10/2026", date(2026, 10, 5), None),  # Indian day/month order
        ("by 2 Jan", date(2027, 1, 2), None),  # early next year, not months ago
        ("Wed 10.30 a.m.", date(2026, 9, 30), time(10, 30)),
        ("midnight on Sunday", date(2026, 10, 4), time(23, 59)),
    ],
)
def test_resolve(phrase: str, day: date, clock: time | None) -> None:
    resolved = resolve(phrase, MONDAY)
    assert resolved is not None
    assert (resolved.day, resolved.clock) == (day, clock)


@pytest.mark.parametrize("phrase", ["as soon as possible", "end of the semester", "31 February"])
def test_unreadable_phrases_return_none(phrase: str) -> None:
    assert resolve(phrase, MONDAY) is None


def test_words_containing_weekday_letters_are_not_weekdays() -> None:
    # "sunday" inside "sundae", "mon" inside "monitor": whole words only
    assert resolve("bring the monitor and a sundae", MONDAY) is None


def test_read_time_edge_cases() -> None:
    assert read_time("12 pm") == time(12, 0)
    assert read_time("12:30 am") == time(0, 30)
    assert read_time("room 204") is None
