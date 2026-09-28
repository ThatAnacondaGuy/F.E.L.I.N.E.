"""Small time helpers. Every datetime in Meow is timezone-aware."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    return datetime.now(UTC)


def require_aware(value: datetime, name: str = "datetime") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def ceil_to(moment: datetime, minutes: int) -> datetime:
    """Round up to the next multiple of ``minutes`` past the hour (no-op if already aligned)."""
    step = timedelta(minutes=minutes)
    floored = moment.replace(second=0, microsecond=0)
    floored -= timedelta(minutes=floored.minute % minutes)
    return floored if floored == moment else floored + step


def format_duration(minutes: float) -> str:
    """45 -> '45m', 150 -> '2h 30m', 3000 -> '2d 2h'."""
    total = round(minutes)
    if total < 60:
        return f"{total}m"
    days, rem = divmod(total, 24 * 60)
    hours, mins = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h" if hours else f"{days}d"
    return f"{hours}h {mins}m" if mins else f"{hours}h"


@dataclass(frozen=True, slots=True)
class Interval:
    """A half-open span of time ``[start, end)``."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        require_aware(self.start, "start")
        require_aware(self.end, "end")
        if self.end <= self.start:
            raise ValueError(f"empty interval {self.start.isoformat()} .. {self.end.isoformat()}")

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60

    def overlaps(self, other: Interval) -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    def clip(self, start: datetime, end: datetime) -> Interval | None:
        lo, hi = max(self.start, start), min(self.end, end)
        return Interval(lo, hi) if lo < hi else None

    def subtract(self, other: Interval) -> list[Interval]:
        if not self.overlaps(other):
            return [self]
        pieces = []
        if self.start < other.start:
            pieces.append(Interval(self.start, other.start))
        if other.end < self.end:
            pieces.append(Interval(other.end, self.end))
        return pieces
