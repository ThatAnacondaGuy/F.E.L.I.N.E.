"""Fits scored tasks into focus time.

Rule: tasks are placed in priority order, each into the earliest free focus time before its
deadline, in sessions no longer than ``max_session_minutes``, with a buffer between sessions
and a daily cap. A task short enough for one session isn't split if it fits whole in a later
slot before it's due. Whatever doesn't fit is reported, never silently dropped.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from meow.config import PlannerConfig
from meow.domain.schedule import WeeklySchedule
from meow.domain.timeutil import Interval, ceil_to, format_duration, require_aware


@dataclass(frozen=True, slots=True)
class PlanTask:
    id: str
    title: str
    remaining_minutes: int
    due_at: datetime | None
    score: float


@dataclass(frozen=True, slots=True)
class Session:
    task_id: str
    title: str
    interval: Interval
    day: date  # the local day whose focus block this session sits in


@dataclass(frozen=True, slots=True)
class Shortfall:
    task_id: str
    title: str
    missing_minutes: int
    at_risk: bool  # True when a deadline will be missed; False when merely deferred
    reason: str


@dataclass(frozen=True, slots=True)
class Plan:
    horizon: Interval
    sessions: tuple[Session, ...]
    shortfalls: tuple[Shortfall, ...]

    @property
    def at_risk(self) -> tuple[Shortfall, ...]:
        return tuple(s for s in self.shortfalls if s.at_risk)

    def sessions_on(self, day: date) -> list[Session]:
        return [s for s in self.sessions if s.day == day]

    def minutes_by_day(self) -> dict[date, float]:
        totals: dict[date, float] = defaultdict(float)
        for s in self.sessions:
            totals[s.day] += s.interval.minutes
        return dict(totals)


@dataclass(slots=True)
class _Free:
    start: datetime
    end: datetime
    day: date


@dataclass
class Planner:
    schedule: WeeklySchedule
    config: PlannerConfig
    _day_cap: int = field(init=False)

    def __post_init__(self) -> None:
        self._day_cap = round(self.config.max_focus_hours_per_day * 60)

    def plan(self, tasks: Sequence[PlanTask], busy: Sequence[Interval], now: datetime) -> Plan:
        require_aware(now, "now")
        cfg = self.config
        start = ceil_to(now, cfg.granularity_minutes)
        horizon = Interval(start, start + timedelta(days=cfg.horizon_days))
        free = self._free_time(horizon, busy)
        used: dict[date, int] = defaultdict(int)
        sessions: list[Session] = []
        shortfalls: list[Shortfall] = []
        buffer = timedelta(minutes=cfg.buffer_minutes)

        ordered = sorted(
            (t for t in tasks if t.remaining_minutes > 0),
            key=lambda t: (-t.score, t.due_at or horizon.end, t.id),
        )
        for task in ordered:
            remaining = task.remaining_minutes
            deadline = horizon.end
            if task.due_at and horizon.start < task.due_at < horizon.end:
                deadline = task.due_at  # overdue work is still scheduled, as soon as possible
            for index, slot in enumerate(free):
                if remaining <= 0 or slot.start >= deadline:
                    break  # slots are chronological, so nothing later can help
                # Keep filling this window (with buffers) until it, the day, or the task runs out.
                while remaining > 0 and slot.start < min(slot.end, deadline):
                    chunk = self._room(slot, deadline, used, remaining)
                    if chunk <= 0 or (chunk < cfg.min_session_minutes and chunk < remaining):
                        break
                    if chunk < remaining <= cfg.max_session_minutes and any(
                        self._room(later, deadline, used, remaining) >= remaining
                        for later in free[index + 1 :]
                    ):
                        break  # don't split work that fits whole in a later slot before it's due
                    begin = slot.start
                    end = begin + timedelta(minutes=chunk)
                    sessions.append(Session(task.id, task.title, Interval(begin, end), slot.day))
                    used[slot.day] += chunk
                    remaining -= chunk
                    slot.start = end + buffer
            free = [s for s in free if s.end - s.start >= timedelta(minutes=1)]
            if remaining > 0:
                shortfalls.append(self._shortfall(task, remaining, horizon))

        sessions.sort(key=lambda s: s.interval.start)
        return Plan(horizon=horizon, sessions=tuple(sessions), shortfalls=tuple(shortfalls))

    def _room(self, slot: _Free, deadline: datetime, used: dict[date, int], wanted: int) -> int:
        """Minutes that could be placed at the start of ``slot`` right now."""
        if slot.start >= deadline:
            return 0
        usable = (min(slot.end, deadline) - slot.start).total_seconds() / 60
        return int(
            min(wanted, self.config.max_session_minutes, usable, self._day_cap - used[slot.day])
        )

    def _free_time(self, horizon: Interval, busy: Sequence[Interval]) -> list[_Free]:
        buffer = timedelta(minutes=self.config.buffer_minutes)
        padded = [Interval(b.start - buffer, b.end + buffer) for b in busy]
        free: list[_Free] = []
        for occ in self.schedule.focus_windows(horizon.start, horizon.end):
            pieces = [occ.interval]
            for block in padded:
                pieces = [p for piece in pieces for p in piece.subtract(block)]
            free.extend(_Free(p.start, p.end, occ.day) for p in pieces)
        return sorted(free, key=lambda f: f.start)

    def _shortfall(self, task: PlanTask, missing: int, horizon: Interval) -> Shortfall:
        need = format_duration(missing)
        if task.due_at and task.due_at <= horizon.start:
            return Shortfall(
                task.id,
                task.title,
                missing,
                True,
                f"Already overdue and {need} still doesn't fit this week",
            )
        if task.due_at and task.due_at <= horizon.end:
            due = task.due_at.astimezone(self.schedule.tz).strftime("%a %d %b %H:%M")
            return Shortfall(
                task.id,
                task.title,
                missing,
                True,
                f"Needs {need} more focus time before it's due ({due})",
            )
        return Shortfall(
            task.id,
            task.title,
            missing,
            False,
            f"{need} didn't fit in the next {self.config.horizon_days} days",
        )
