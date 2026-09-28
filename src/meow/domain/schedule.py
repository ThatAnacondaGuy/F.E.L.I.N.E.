"""The weekly rhythm (sleep, college, focus...) turned into concrete time intervals."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import combinations
from zoneinfo import ZoneInfo

from meow.config import WEEKDAYS, ScheduleBlock
from meow.domain.timeutil import Interval, require_aware
from meow.types import BlockKind

# When blocks overlap (a config mistake, but possible), the stricter one wins.
_PRECEDENCE = {BlockKind.SLEEP: 0, BlockKind.COLLEGE: 1, BlockKind.ROUTINE: 2, BlockKind.FOCUS: 3}


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One concrete instance of a schedule block."""

    block: ScheduleBlock
    interval: Interval
    day: date  # local date the block starts on; a 16:30-04:00 block belongs to its start day


class WeeklySchedule:
    def __init__(self, blocks: Sequence[ScheduleBlock], tz: ZoneInfo) -> None:
        self.blocks = tuple(blocks)
        self.tz = tz

    def occurrences(self, start: datetime, end: datetime) -> list[Occurrence]:
        """All block occurrences overlapping ``[start, end)``, unclipped, sorted by start."""
        require_aware(start, "start")
        require_aware(end, "end")
        first = start.astimezone(self.tz).date() - timedelta(days=1)  # catch last night's block
        last = end.astimezone(self.tz).date()
        window = Interval(start, end)
        found: list[Occurrence] = []
        day = first
        while day <= last:
            weekday = WEEKDAYS[day.weekday()]
            for block in self.blocks:
                if weekday not in block.days:
                    continue
                begin = datetime.combine(day, block.start, tzinfo=self.tz)
                finish_day = day + timedelta(days=1) if block.crosses_midnight else day
                finish = datetime.combine(finish_day, block.end, tzinfo=self.tz)
                interval = Interval(begin, finish)
                if interval.overlaps(window):
                    found.append(Occurrence(block, interval, day))
            day += timedelta(days=1)
        return sorted(found, key=lambda o: (o.interval.start, _PRECEDENCE[o.block.kind]))

    def focus_windows(self, start: datetime, end: datetime) -> list[Occurrence]:
        """Focus time within ``[start, end)``, clipped to it."""
        windows = []
        for occ in self.occurrences(start, end):
            if occ.block.kind is not BlockKind.FOCUS:
                continue
            clipped = occ.interval.clip(start, end)
            if clipped:
                windows.append(Occurrence(occ.block, clipped, occ.day))
        return windows

    def block_at(self, moment: datetime) -> ScheduleBlock | None:
        active = [
            o
            for o in self.occurrences(moment, moment + timedelta(minutes=1))
            if o.interval.contains(moment)
        ]
        if not active:
            return None
        return min(active, key=lambda o: _PRECEDENCE[o.block.kind]).block

    def next_start(self, kind: BlockKind, after: datetime) -> datetime | None:
        """Start of the next block of ``kind`` strictly after ``after`` (within a week)."""
        for occ in self.occurrences(after, after + timedelta(days=8)):
            if occ.block.kind is kind and occ.interval.start > after:
                return occ.interval.start
        return None

    def is_quiet(self, moment: datetime) -> bool:
        block = self.block_at(moment)
        return block is not None and block.kind is BlockKind.SLEEP

    def weekly_focus_hours(self) -> float:
        monday = datetime(2024, 1, 1, tzinfo=self.tz)  # any Monday
        windows = self.focus_windows(monday, monday + timedelta(days=7))
        return sum(o.interval.minutes for o in windows) / 60

    def overlaps(self) -> list[tuple[Occurrence, Occurrence]]:
        """Pairs of blocks that overlap during a typical week (should be empty)."""
        monday = datetime(2024, 1, 1, tzinfo=self.tz)
        occs = self.occurrences(monday, monday + timedelta(days=8))
        return [(a, b) for a, b in combinations(occs, 2) if a.interval.overlaps(b.interval)]
