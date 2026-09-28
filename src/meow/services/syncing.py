"""One entry point for "go fetch everything", used by the CLI, the API and the background worker."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from meow.config import Settings
from meow.domain.timeutil import utcnow
from meow.integrations.google.auth import KeychainTokenStore, TokenStore, load_credentials
from meow.integrations.google.sync import APIs, CredentialLoader, GoogleAPIs, GoogleSync, SyncReport
from meow.llm.extraction import Extractor
from meow.llm.ollama import JSONChat
from meow.services import accounts, audit
from meow.services.capture import ExtractionRun, extract_pending
from meow.types import SourceKind

log = logging.getLogger(__name__)
_lock = threading.Lock()


class SyncBusy(RuntimeError):
    pass


@dataclass(slots=True)
class FullSync:
    google: SyncReport
    extraction: ExtractionRun = field(default_factory=ExtractionRun)


def run_sync(
    db: Session,
    settings: Settings,
    now: datetime,
    *,
    llm: JSONChat | None,
    apis: APIs | None = None,
    store: TokenStore | None = None,
    load: CredentialLoader = load_credentials,
    account: str | None = None,
    source: SourceKind | None = None,
) -> FullSync:
    """Sync connected accounts, then let the model read what's new (if ``llm`` is given)."""
    if not _lock.acquire(blocking=False):
        raise SyncBusy("a sync is already running")
    try:
        profile = settings.profile
        google = GoogleSync(
            db, profile, store or KeychainTokenStore(settings), apis or GoogleAPIs(), now, load
        ).run(account=account, source=source)
        full = FullSync(google=google)
        if llm is not None:
            full.extraction = extract_pending(
                db, profile, Extractor(llm, profile), now, profile.sync.extract_batch
            )
        audit.record(
            db,
            actor="sync",
            action="sync.completed",
            new=google.new_items,
            proposals=google.proposals + full.extraction.proposals,
            errors=len(google.errors),
            extraction_error=full.extraction.error,
        )
        db.commit()
        return full
    finally:
        _lock.release()


class SyncWorker(threading.Thread):
    """Background sync while the server runs. Sleeps ``interval`` minutes between runs."""

    def __init__(
        self,
        settings: Settings,
        sessions: sessionmaker[Session],
        clock: Callable[[], datetime] = utcnow,
        llm_factory: Callable[[], JSONChat] | None = None,
        first_delay: float = 20.0,
    ) -> None:
        super().__init__(name="meow-sync", daemon=True)
        self.settings, self.sessions, self.clock = settings, sessions, clock
        self.llm_factory = llm_factory
        self.first_delay = first_delay
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        interval = self.settings.profile.sync.interval_minutes * 60
        if self._stop.wait(self.first_delay):
            return
        while not self._stop.is_set():
            self.tick()
            if self._stop.wait(interval):
                return

    def tick(self) -> None:
        try:
            with self.sessions() as db:
                if not accounts.list_accounts(db, enabled_only=True):
                    return
                llm = self.llm_factory() if self.llm_factory else None
                result = run_sync(db, self.settings, self.clock(), llm=llm)
                log.info(
                    "background sync: %d new items, %d proposals",
                    result.google.new_items,
                    result.google.proposals,
                )
        except SyncBusy:
            log.info("background sync skipped: another sync is running")
        except Exception:
            log.exception("background sync failed")
