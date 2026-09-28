"""Morning and evening briefings, built from your real plan, deadlines and inbox.

Deterministic on purpose: no model is involved, so a briefing is instant and never invents a
deadline. One of each kind per day; notifications are never sent during quiet hours.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from meow.config import Profile
from meow.db.models import Briefing, FocusSession, Task
from meow.domain.timeutil import format_duration
from meow.notify import Notifier
from meow.services import accounts, audit, proposals, tasks
from meow.types import BlockKind, BriefingKind, ProposalStatus, TaskStatus

TOP = 3


@dataclass(frozen=True, slots=True)
class Section:
    heading: str
    items: list[str]
    tone: str = ""  # "risk" for things that need attention


@dataclass(slots=True)
class Draft:
    kind: BriefingKind
    day: date
    headline: str
    sections: list[Section] = field(default_factory=list)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


class Composer:
    def __init__(self, db: Session, profile: Profile, now: datetime) -> None:
        self.db, self.profile, self.now = db, profile, now
        self.tz = profile.user.tz
        self.schedule = tasks.schedule_for(profile)
        # The awake day ends when the next sleep block starts.
        self.day_end = self.schedule.next_start(BlockKind.SLEEP, now) or now + timedelta(hours=24)

    def _t(self, moment: datetime, fmt: str = "%H:%M") -> str:
        return moment.astimezone(self.tz).strftime(fmt)

    def _booked(self, until: datetime) -> list[FocusSession]:
        return list(
            self.db.scalars(
                select(FocusSession)
                .join(Task)
                .where(
                    FocusSession.end_at > self.now,
                    FocusSession.start_at < until,
                    Task.status == TaskStatus.TODO,
                )
                .order_by(FocusSession.start_at)
            )
        )

    def _due_before(self, until: datetime) -> list[Task]:
        return [t for t in tasks.open_tasks(self.db) if t.due_at and t.due_at <= until]

    def _due_line(self, task: Task) -> str:
        assert task.due_at is not None
        left = (task.due_at - self.now).total_seconds() / 60
        when = self._t(task.due_at, "%a %H:%M")
        return f"{task.title}: {when} " + (
            f"(overdue by {format_duration(-left)})"
            if left < 0
            else f"(in {format_duration(left)})"
        )

    def _waiting(self) -> list[str]:
        items = []
        pending = len(proposals.list_proposals(self.db, ProposalStatus.PENDING))
        if pending:
            items.append(f"{_plural(pending, 'proposal')} in your inbox")
        for acct in accounts.list_accounts(self.db, enabled_only=True):
            if acct.needs_reauth:
                items.append(f"Sign in again: meow google login {acct.email}")
        return items

    def _risk(self) -> list[str]:
        plan = tasks.build_plan(self.db, self.profile, self.now)
        return [f"{s.title}: {s.reason}" for s in plan.at_risk]

    def morning(self) -> Draft:
        blocks = [
            f"{self._t(o.interval.start)}–{self._t(o.interval.end)} {o.block.name}"
            for o in self.schedule.occurrences(self.now, self.day_end)
            if o.block.kind is not BlockKind.SLEEP and o.interval.end > self.now
        ]
        booked = self._booked(self.day_end)
        focus = [f"{self._t(s.start_at)}–{self._t(s.end_at)} {s.task.title}" for s in booked]
        if not focus:
            suggested = [
                s
                for s in tasks.build_plan(self.db, self.profile, self.now).sessions
                if s.interval.start < self.day_end
            ]
            if suggested:
                focus = [
                    f"None approved yet. The planner suggests {_plural(len(suggested), 'block')}"
                    " — open Meow to review them."
                ]
        due = self._due_before(self.now + timedelta(hours=48))
        risk = self._risk()
        top = [
            f"{r.task.title} ({r.score.top_reasons(1)[0]})"
            if r.score.top_reasons(1)
            else r.task.title
            for r in tasks.ranked_tasks(self.db, self.profile, self.now)[:TOP]
        ]
        parts = [
            p
            for p in (
                _plural(len(booked), "focus block") + " today" if booked else "",
                f"{len(due)} due in 48h" if due else "",
                f"{len(risk)} at risk" if risk else "",
            )
            if p
        ]
        headline = " · ".join(parts) or "A clear day: nothing due in the next 48 hours."
        return Draft(
            BriefingKind.MORNING,
            self.now.astimezone(self.tz).date(),
            headline,
            [
                s
                for s in (
                    Section("Today", blocks),
                    Section("Focus blocks", focus),
                    Section("Due in the next 48 hours", [self._due_line(t) for t in due]),
                    Section("At risk", risk, "risk"),
                    Section("Top priorities", top),
                    Section("Waiting for you", self._waiting()),
                )
                if s.items
            ],
        )

    def evening(self) -> Draft:
        last_sleep_end = max(
            (
                o.interval.end
                for o in self.schedule.occurrences(self.now - timedelta(days=1), self.now)
                if o.block.kind is BlockKind.SLEEP and o.interval.end <= self.now
            ),
            default=self.now - timedelta(hours=24),
        )
        done = list(
            self.db.scalars(
                select(Task)
                .where(Task.status == TaskStatus.DONE, Task.completed_at >= last_sleep_end)
                .order_by(Task.completed_at)
            )
        )
        tonight = self._booked(self.day_end)
        tomorrow_end = datetime.combine(
            self.now.astimezone(self.tz).date() + timedelta(days=1), datetime.max.time(), self.tz
        )
        due = self._due_before(tomorrow_end)
        risk = self._risk()
        parts = [
            f"{len(done)} done today",
            _plural(len(tonight), "block") + " left tonight" if tonight else "",
            f"{len(due)} due by tomorrow" if due else "",
            f"{len(risk)} at risk" if risk else "",
        ]
        return Draft(
            BriefingKind.EVENING,
            self.now.astimezone(self.tz).date(),
            " · ".join(p for p in parts if p),
            [
                s
                for s in (
                    Section("Done today", [t.title for t in done]),
                    Section(
                        "Still ahead tonight",
                        [
                            f"{self._t(s.start_at)}–{self._t(s.end_at)} {s.task.title}"
                            for s in tonight
                        ],
                    ),
                    Section("Due by tomorrow", [self._due_line(t) for t in due]),
                    Section("At risk", risk, "risk"),
                    Section("Waiting for you", self._waiting()),
                )
                if s.items
            ],
        )


def compose(db: Session, profile: Profile, kind: BriefingKind, now: datetime) -> Draft:
    composer = Composer(db, profile, now)
    return composer.morning() if kind is BriefingKind.MORNING else composer.evening()


def generate(
    db: Session,
    profile: Profile,
    kind: BriefingKind,
    now: datetime,
    notifier: Notifier,
    *,
    force: bool = False,
) -> Briefing:
    """Create today's briefing of ``kind`` (once per day unless ``force``) and notify."""
    day = now.astimezone(profile.user.tz).date()
    existing = db.scalar(select(Briefing).where(Briefing.kind == kind.value, Briefing.day == day))
    if existing is not None and not force:
        return existing
    proposals.expire_stale(db, now)
    draft = compose(db, profile, kind, now)
    row = existing or Briefing(kind=kind.value, day=day)
    row.headline = draft.headline[:300]
    row.sections = [
        {"heading": s.heading, "items": s.items, "tone": s.tone} for s in draft.sections
    ]
    row.created_at = now
    db.add(row)
    quiet = tasks.schedule_for(profile).is_quiet(now)
    if profile.briefings.notify and not quiet and not row.notified:
        row.notified = notifier.notify(f"Meow · {kind.value.title()} briefing", draft.headline)
    audit.record(
        db,
        actor="meow",
        action="briefing.created",
        entity_type="briefing",
        kind=kind.value,
        day=day.isoformat(),
        notified=row.notified,
        quiet=quiet,
    )
    db.commit()
    return row


def latest(db: Session, profile: Profile, now: datetime) -> Briefing | None:
    day = now.astimezone(profile.user.tz).date()
    return db.scalar(
        select(Briefing).where(Briefing.day == day).order_by(Briefing.created_at.desc()).limit(1)
    )
