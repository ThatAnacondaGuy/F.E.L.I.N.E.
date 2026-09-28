"""Deterministic, explainable task scoring.

No keyword guessing: career relevance and course come from structured fields set at
extraction time (by the model, with evidence) or by you. Every score carries its reasons.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from meow.config import Course, ScoringConfig
from meow.domain.timeutil import format_duration, require_aware
from meow.types import CoursePriority, Importance

IMPORTANCE_VALUE = {
    Importance.LOW: 0.25,
    Importance.MEDIUM: 0.5,
    Importance.HIGH: 0.75,
    Importance.CRITICAL: 1.0,
}
COURSE_VALUE = {
    CoursePriority.HIGHEST: 1.0,
    CoursePriority.HIGH: 0.75,
    CoursePriority.STANDARD: 0.5,
}


@dataclass(frozen=True, slots=True)
class TaskFacts:
    """What the scorer needs to know about a task, independent of storage."""

    title: str
    importance: Importance
    due_at: datetime | None
    estimated_minutes: int | None
    course_code: str | None
    career_relevance: float


@dataclass(frozen=True, slots=True)
class Factor:
    name: str
    value: float  # 0..1
    weight: float
    reason: str

    @property
    def points(self) -> float:
        return self.value * self.weight * 100


@dataclass(frozen=True, slots=True)
class Score:
    total: float  # 0..100
    factors: tuple[Factor, ...]

    def top_reasons(self, limit: int = 3) -> list[str]:
        ranked = sorted((f for f in self.factors if f.points > 0), key=lambda f: -f.points)
        return [f.reason for f in ranked[:limit]]


class Prioritizer:
    def __init__(self, config: ScoringConfig, courses: Sequence[Course]) -> None:
        self.config = config
        self.courses = {c.code: c for c in courses}

    def score(self, task: TaskFacts, now: datetime) -> Score:
        require_aware(now, "now")
        w = self.config.weights
        factors = (
            self._urgency(task, now, w.urgency),
            self._importance(task, w.importance),
            self._career(task, w.career),
            self._academic(task, w.academic),
            self._quick_win(task, w.quick_win),
        )
        total = round(sum(f.points for f in factors), 1)
        return Score(total=total, factors=factors)

    def _urgency(self, task: TaskFacts, now: datetime, weight: float) -> Factor:
        if task.due_at is None:
            return Factor("urgency", 0.0, weight, "No deadline")
        require_aware(task.due_at, "due_at")
        hours_left = (task.due_at - now).total_seconds() / 3600
        if hours_left <= 0:
            overdue = format_duration(-hours_left * 60)
            return Factor("urgency", 1.0, weight, f"Overdue by {overdue}")
        work_minutes = task.estimated_minutes or self.config.default_estimate_minutes
        slack = hours_left - work_minutes / 60
        value = 1.0 if slack <= 0 else 0.5 ** (slack / self.config.urgency_half_life_hours)
        reason = (
            f"Due in {format_duration(hours_left * 60)} (~{format_duration(work_minutes)} of work)"
        )
        if slack <= 0:
            reason += ", no slack left"
        return Factor("urgency", value, weight, reason)

    def _importance(self, task: TaskFacts, weight: float) -> Factor:
        return Factor(
            "importance",
            IMPORTANCE_VALUE[task.importance],
            weight,
            f"Marked {task.importance.value} importance",
        )

    def _career(self, task: TaskFacts, weight: float) -> Factor:
        value = min(1.0, max(0.0, task.career_relevance))
        if value == 0:
            return Factor("career", 0.0, weight, "No career signal")
        return Factor("career", value, weight, f"Career relevance {value:.1f} for your NVIDIA goal")

    def _academic(self, task: TaskFacts, weight: float) -> Factor:
        if not task.course_code:
            return Factor("academic", 0.0, weight, "Not coursework")
        course = self.courses.get(task.course_code)
        if course is None:
            return Factor("academic", 0.0, weight, f"{task.course_code} is not in your course list")
        return Factor(
            "academic",
            COURSE_VALUE[course.priority],
            weight,
            f"{course.name} is a {course.priority.value}-priority course",
        )

    def _quick_win(self, task: TaskFacts, weight: float) -> Factor:
        if task.estimated_minutes is None:
            return Factor("quick_win", 0.5, weight, "No time estimate")
        cap = self.config.quick_win_minutes
        value = max(0.0, 1.0 - task.estimated_minutes / cap)
        size = format_duration(task.estimated_minutes)
        reason = f"Quick win (~{size})" if value >= 0.5 else f"Sizeable task (~{size})"
        return Factor("quick_win", value, weight, reason)
