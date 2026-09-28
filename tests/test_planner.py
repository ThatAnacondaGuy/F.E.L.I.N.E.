from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from meow.config import PlannerConfig, Profile
from meow.domain.planner import Planner, PlanTask
from meow.domain.schedule import WeeklySchedule
from meow.domain.timeutil import Interval

from support import IST, ist

MONDAY_4PM = ist(2026, 9, 28, 16, 0)


@pytest.fixture
def planner(profile: Profile) -> Planner:
    return Planner(WeeklySchedule(profile.schedule, IST), profile.planner)


def task(id: str, minutes: int, score: float = 50, due: datetime | None = None) -> PlanTask:
    return PlanTask(id=id, title=id, remaining_minutes=minutes, due_at=due, score=score)


def test_work_goes_into_focus_time_only(planner: Planner) -> None:
    plan = planner.plan([task("a", 60)], [], MONDAY_4PM)
    (session,) = plan.sessions
    assert session.interval.start == ist(2026, 9, 28, 16, 30)  # not during college
    assert session.interval.end == ist(2026, 9, 28, 17, 30)


def test_higher_score_gets_the_earlier_slot(planner: Planner) -> None:
    plan = planner.plan([task("low", 60, score=20), task("high", 60, score=90)], [], MONDAY_4PM)
    assert [s.task_id for s in plan.sessions] == ["high", "low"]
    gap = plan.sessions[1].interval.start - plan.sessions[0].interval.end
    assert gap == timedelta(minutes=15)  # buffer between sessions


def test_long_tasks_are_split_into_capped_sessions(planner: Planner, profile: Profile) -> None:
    plan = planner.plan([task("big", 300)], [], MONDAY_4PM)
    lengths = [s.interval.minutes for s in plan.sessions]
    assert lengths == [150, 150]
    assert max(lengths) <= profile.planner.max_session_minutes


def test_daily_cap_pushes_work_to_the_next_day(planner: Planner) -> None:
    plan = planner.plan([task("huge", 8 * 60)], [], MONDAY_4PM)
    by_day = plan.minutes_by_day()
    assert by_day[ist(2026, 9, 28).date()] == 6 * 60
    assert by_day[ist(2026, 9, 29).date()] == 2 * 60


def test_sessions_can_cross_midnight(profile: Profile) -> None:
    cfg = profile.planner.model_copy(update={"max_session_minutes": 240})
    planner = Planner(WeeklySchedule(profile.schedule, IST), cfg)
    plan = planner.plan([task("night", 120)], [], ist(2026, 9, 28, 23, 0))
    (session,) = plan.sessions
    assert session.interval.start == ist(2026, 9, 28, 23, 0)
    assert session.interval.end == ist(2026, 9, 29, 1, 0)
    assert session.day == ist(2026, 9, 28).date()  # still Monday's focus block


def test_never_schedules_in_the_past_or_during_sleep(planner: Planner) -> None:
    plan = planner.plan([task("t", 60)], [], ist(2026, 9, 29, 3, 50))
    (session,) = plan.sessions
    # 03:50 rounds up to 04:00, when sleep starts, so the work waits for Tuesday 16:30.
    assert session.interval.start == ist(2026, 9, 29, 16, 30)


def test_busy_calendar_events_are_avoided_with_buffers(planner: Planner) -> None:
    meeting = Interval(ist(2026, 9, 28, 17, 0), ist(2026, 9, 28, 18, 0))
    plan = planner.plan([task("t", 60)], [meeting], MONDAY_4PM)
    (session,) = plan.sessions
    assert session.interval.start == ist(2026, 9, 28, 18, 15)


def test_missed_deadline_is_flagged_not_hidden(planner: Planner) -> None:
    due = ist(2026, 9, 28, 19, 0)  # only 2.5h of focus time before this
    plan = planner.plan([task("report", 240, due=due)], [], MONDAY_4PM)
    assert sum(s.interval.minutes for s in plan.sessions) == 150
    assert all(s.interval.end <= due for s in plan.sessions)
    (risk,) = plan.at_risk
    assert risk.missing_minutes == 90
    assert "before it's due" in risk.reason


def test_overdue_work_is_still_scheduled_as_soon_as_possible(planner: Planner) -> None:
    plan = planner.plan([task("late", 60, due=MONDAY_4PM - timedelta(days=1))], [], MONDAY_4PM)
    (session,) = plan.sessions
    assert session.interval.start == ist(2026, 9, 28, 16, 30)
    assert plan.at_risk == ()


def test_work_without_deadline_that_does_not_fit_is_deferred(profile: Profile) -> None:
    cfg = PlannerConfig(
        horizon_days=1,
        min_session_minutes=30,
        max_session_minutes=150,
        buffer_minutes=15,
        max_focus_hours_per_day=1,
        granularity_minutes=15,
    )
    planner = Planner(WeeklySchedule(profile.schedule, IST), cfg)
    plan = planner.plan([task("someday", 180)], [], MONDAY_4PM)
    (short,) = plan.shortfalls
    assert not short.at_risk
    assert short.missing_minutes == 120


def test_planning_is_deterministic(planner: Planner) -> None:
    tasks = [task(f"t{i}", 45 + i * 10, score=50) for i in range(6)]
    first = planner.plan(tasks, [], MONDAY_4PM)
    second = planner.plan(list(reversed(tasks)), [], MONDAY_4PM)
    assert first == second


def test_short_task_is_not_split_when_it_fits_whole_later(planner: Planner) -> None:
    # The big task eats 330 of Monday's 360-minute cap, leaving a 30-minute sliver.
    big = task("big", 330, score=90)
    lab = task("lab", 90, score=40, due=ist(2026, 10, 2, 23, 59))
    plan = planner.plan([big, lab], [], MONDAY_4PM)
    (lab_session,) = [s for s in plan.sessions if s.task_id == "lab"]
    assert lab_session.interval.start == ist(2026, 9, 29, 16, 30)  # whole, on Tuesday
    assert lab_session.interval.minutes == 90


def test_short_task_is_split_when_the_deadline_leaves_no_choice(planner: Planner) -> None:
    big = task("big", 330, score=90)
    lab = task("lab", 90, score=40, due=ist(2026, 9, 29, 17, 30))
    plan = planner.plan([big, lab], [], MONDAY_4PM)
    lab_sessions = [s for s in plan.sessions if s.task_id == "lab"]
    assert [s.interval.minutes for s in lab_sessions] == [30, 60]
    assert plan.at_risk == ()
