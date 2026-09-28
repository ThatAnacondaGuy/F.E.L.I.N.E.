from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session

from meow.config import Profile
from meow.db.models import CalendarEvent, FocusSession, Task
from meow.domain.planner import Plan, Planner, PlanTask
from meow.domain.prioritizer import Prioritizer, Score, TaskFacts
from meow.domain.schedule import WeeklySchedule
from meow.domain.timeutil import Interval, utcnow
from meow.services import audit
from meow.types import Category, Importance, TaskStatus


class TaskDraft(BaseModel):
    """A validated description of a task, from you or from a proposal."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    notes: str = ""
    importance: Importance = Importance.MEDIUM
    category: Category = Category.PERSONAL
    due_at: AwareDatetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=24 * 60 * 14)
    course_code: str | None = None
    career_relevance: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("course_code")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None


class TaskNotFound(LookupError):
    pass


def create_task(
    db: Session,
    draft: TaskDraft,
    *,
    actor: str,
    source_item_id: str | None = None,
    proposal_id: str | None = None,
) -> Task:
    task = Task(
        **draft.model_dump(),
        source_item_id=source_item_id,
        proposal_id=proposal_id,
    )
    db.add(task)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action="task.created",
        entity_type="task",
        entity_id=task.id,
        title=task.title,
        via_proposal=proposal_id,
    )
    return task


def add_task(db: Session, draft: TaskDraft, *, actor: str = "user") -> Task:
    """Create a task directly (you typed it, so no proposal is needed)."""
    task = create_task(db, draft, actor=actor)
    db.commit()
    return task


def get_task(db: Session, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise TaskNotFound(task_id)
    return task


def set_status(
    db: Session, task_id: str, status: TaskStatus, *, actor: str, now: datetime | None = None
) -> Task:
    task = get_task(db, task_id)
    task.status = status
    now = now or utcnow()
    task.completed_at = now if status is TaskStatus.DONE else None
    cleared = 0
    if status is not TaskStatus.TODO:
        # Finished or dropped: its upcoming focus blocks free up (and leave the calendar
        # on the next sync). Past blocks stay as history.
        result = db.execute(
            delete(FocusSession).where(FocusSession.task_id == task.id, FocusSession.start_at > now)
        )
        cleared = cast(CursorResult[Any], result).rowcount
    audit.record(
        db,
        actor=actor,
        action=f"task.{status.value}",
        entity_type="task",
        entity_id=task.id,
        title=task.title,
        focus_blocks_cleared=cleared,
    )
    db.commit()
    return task


def open_tasks(db: Session) -> list[Task]:
    stmt = select(Task).where(Task.status == TaskStatus.TODO).order_by(Task.created_at)
    return list(db.scalars(stmt))


def facts(task: Task) -> TaskFacts:
    return TaskFacts(
        title=task.title,
        importance=task.importance,
        due_at=task.due_at,
        estimated_minutes=task.estimated_minutes,
        course_code=task.course_code,
        career_relevance=task.career_relevance,
    )


@dataclass(frozen=True, slots=True)
class RankedTask:
    task: Task
    score: Score


def ranked_tasks(db: Session, profile: Profile, now: datetime) -> list[RankedTask]:
    prioritizer = Prioritizer(profile.scoring, profile.courses)
    ranked = [RankedTask(t, prioritizer.score(facts(t), now)) for t in open_tasks(db)]
    return sorted(ranked, key=lambda r: (-r.score.total, r.task.due_at or now, r.task.id))


def schedule_for(profile: Profile) -> WeeklySchedule:
    return WeeklySchedule(profile.schedule, profile.user.tz)


def build_plan(db: Session, profile: Profile, now: datetime) -> Plan:
    """Plan open tasks around calendar events and already-approved focus sessions.

    Approved future sessions count as busy time and as progress on their task, so
    re-planning never double-books. Past sessions are not counted as work done yet.
    """
    horizon_end = now + timedelta(days=profile.planner.horizon_days + 1)
    events = db.scalars(
        select(CalendarEvent).where(
            CalendarEvent.busy.is_(True),
            CalendarEvent.end_at > now,
            CalendarEvent.start_at < horizon_end,
        )
    )
    sessions = list(db.scalars(select(FocusSession).where(FocusSession.end_at > now)))
    busy = [Interval(e.start_at, e.end_at) for e in events]
    busy += [Interval(s.start_at, s.end_at) for s in sessions]

    booked: dict[str, float] = {}
    for s in sessions:
        booked[s.task_id] = booked.get(s.task_id, 0) + (s.end_at - s.start_at).total_seconds() / 60

    default = profile.scoring.default_estimate_minutes
    plan_tasks = [
        PlanTask(
            id=r.task.id,
            title=r.task.title,
            remaining_minutes=max(
                0, round((r.task.estimated_minutes or default) - booked.get(r.task.id, 0))
            ),
            due_at=r.task.due_at,
            score=r.score.total,
        )
        for r in ranked_tasks(db, profile, now)
    ]
    return Planner(schedule_for(profile), profile.planner).plan(plan_tasks, busy, now)
