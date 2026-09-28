"""The background worker that runs while `meow serve` does: sync on an interval (or right away
when nudged), and briefings at their scheduled times."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from meow.config import Settings
from meow.domain.timeutil import utcnow
from meow.llm.ollama import JSONChat
from meow.notify import Notifier
from meow.services import accounts, briefings, syncing
from meow.types import BriefingKind

log = logging.getLogger(__name__)
Sessions = sessionmaker[Session]


class Job(Protocol):
    name: str

    def due(self, now: datetime) -> bool: ...
    def run(self, sessions: Sessions, now: datetime) -> None: ...


class SyncJob:
    name = "sync"

    def __init__(self, settings: Settings, llm_factory: Callable[[], JSONChat] | None) -> None:
        self.settings, self.llm_factory = settings, llm_factory
        self.interval = timedelta(minutes=settings.profile.sync.interval_minutes)
        self.last_run: datetime | None = None
        self.nudged = False

    def due(self, now: datetime) -> bool:
        if self.nudged:
            return True
        if not self.interval:
            return False
        return self.last_run is None or now - self.last_run >= self.interval

    def run(self, sessions: Sessions, now: datetime) -> None:
        with sessions() as db:
            if accounts.list_accounts(db, enabled_only=True):
                llm = self.llm_factory() if self.llm_factory else None
                try:
                    result = syncing.run_sync(db, self.settings, now, llm=llm)
                except syncing.SyncBusy:
                    return  # stay due; try again next tick
                log.info(
                    "sync: %d new, %d proposals, %d pushed",
                    result.google.new_items,
                    result.google.proposals,
                    sum(r.pushed for r in result.google.results),
                )
        self.last_run, self.nudged = now, False


class BriefingJob:
    name = "briefings"

    def __init__(self, settings: Settings, notifier: Notifier) -> None:
        self.settings, self.notifier = settings, notifier
        self._done: set[tuple[BriefingKind, date]] = set()

    def pending(self, now: datetime) -> list[BriefingKind]:
        cfg, tz = self.settings.profile.briefings, self.settings.profile.user.tz
        local = now.astimezone(tz)
        grace = timedelta(hours=cfg.grace_hours)
        due = []
        for kind, at in ((BriefingKind.MORNING, cfg.morning), (BriefingKind.EVENING, cfg.evening)):
            scheduled = datetime.combine(local.date(), at, tzinfo=tz)
            if scheduled <= now < scheduled + grace and (kind, local.date()) not in self._done:
                due.append(kind)
        return due

    def due(self, now: datetime) -> bool:
        return bool(self.pending(now))

    def run(self, sessions: Sessions, now: datetime) -> None:
        day = now.astimezone(self.settings.profile.user.tz).date()
        with sessions() as db:
            for kind in self.pending(now):
                briefings.generate(db, self.settings.profile, kind, now, self.notifier)
                self._done.add((kind, day))


class Worker(threading.Thread):
    def __init__(
        self,
        sessions: Sessions,
        jobs: Sequence[Job],
        clock: Callable[[], datetime] = utcnow,
        tick_seconds: float = 30.0,
        first_delay: float = 20.0,
    ) -> None:
        super().__init__(name="meow-worker", daemon=True)
        self.sessions, self.jobs, self.clock = sessions, list(jobs), clock
        self.tick_seconds, self.first_delay = tick_seconds, first_delay
        self._stop, self._wake = threading.Event(), threading.Event()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def nudge_sync(self) -> None:
        """Sync soon (e.g. focus blocks were just approved and should reach the calendar)."""
        for job in self.jobs:
            if isinstance(job, SyncJob):
                job.nudged = True
        self._wake.set()

    def run(self) -> None:
        if self._stop.wait(self.first_delay):
            return
        while not self._stop.is_set():
            self.tick()
            self._wake.wait(self.tick_seconds)
            self._wake.clear()

    def tick(self) -> None:
        now = self.clock()
        for job in self.jobs:
            try:
                if job.due(now):
                    job.run(self.sessions, now)
            except Exception:
                log.exception("background job %s failed", job.name)
