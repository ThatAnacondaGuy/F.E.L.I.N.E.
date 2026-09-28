"""One entry point for "go fetch everything", used by the CLI, the API and the background worker."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from meow.config import Settings
from meow.integrations.google.auth import KeychainTokenStore, TokenStore, load_credentials
from meow.integrations.google.sync import APIs, CredentialLoader, GoogleAPIs, GoogleSync, SyncReport
from meow.llm.extraction import Extractor
from meow.llm.ollama import JSONChat
from meow.services import audit, proposals
from meow.services.capture import ExtractionRun, extract_pending
from meow.types import SourceKind

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
        proposals.expire_stale(db, now)
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
