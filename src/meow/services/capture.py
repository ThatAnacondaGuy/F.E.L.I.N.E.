"""Ingest a piece of text: keep it as a source, extract tasks, and file them as proposals."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from meow.config import Profile
from meow.db.models import Proposal, SourceItem
from meow.domain.timeutil import utcnow
from meow.llm.extraction import ExtractionError, Extractor, SourceText
from meow.services import audit, proposals
from meow.types import ProposalKind, SourceKind


@dataclass(slots=True)
class CaptureResult:
    source: SourceItem
    proposals: list[Proposal] = field(default_factory=list)
    dropped: list[tuple[str, str]] = field(default_factory=list)
    duplicate: bool = False


def content_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


class Change(StrEnum):
    NEW = "new"
    CHANGED = "changed"
    SAME = "same"


def upsert_source(
    db: Session,
    *,
    kind: SourceKind,
    body: str,
    external_id: str | None = None,
    account: str = "",
    title: str = "",
    author: str | None = None,
    url: str | None = None,
    occurred_at: datetime | None = None,
) -> tuple[SourceItem, Change]:
    """Insert a source, or update it if its content changed (a teacher edits a deadline)."""
    digest = content_hash(title, body)
    ext = external_id or digest
    existing = db.scalar(
        select(SourceItem).where(
            SourceItem.kind == kind, SourceItem.account == account, SourceItem.external_id == ext
        )
    )
    if existing is not None:
        if existing.content_hash == digest:
            return existing, Change.SAME
        existing.title, existing.body, existing.author, existing.url = title, body, author, url
        existing.occurred_at = occurred_at or existing.occurred_at
        existing.content_hash, existing.extracted_at, existing.extraction_error = digest, None, None
        audit.record(
            db,
            actor="meow",
            action="source.changed",
            entity_type="source",
            entity_id=existing.id,
            kind=kind.value,
        )
        return existing, Change.CHANGED
    item = SourceItem(
        kind=kind,
        account=account,
        external_id=ext,
        title=title,
        body=body,
        author=author,
        url=url,
        occurred_at=occurred_at,
        content_hash=digest,
    )
    db.add(item)
    db.flush()
    audit.record(
        db,
        actor="meow",
        action="source.stored",
        entity_type="source",
        entity_id=item.id,
        kind=kind.value,
    )
    return item, Change.NEW


def store_source(db: Session, **fields: Any) -> tuple[SourceItem, bool]:
    """Insert a source item, or return the existing one unchanged. Returns (item, created)."""
    digest = content_hash(fields.get("title", ""), fields["body"])
    ext = fields.get("external_id") or digest
    existing = db.scalar(
        select(SourceItem).where(
            SourceItem.kind == fields["kind"],
            SourceItem.account == fields.get("account", ""),
            SourceItem.external_id == ext,
        )
    )
    if existing is not None:
        return existing, False
    item, _ = upsert_source(db, **fields)
    return item, True


def extract_into_proposals(
    db: Session, profile: Profile, extractor: Extractor, item: SourceItem, now: datetime
) -> CaptureResult:
    result = CaptureResult(source=item)
    text = SourceText(
        body=item.body,
        title=item.title,
        author=item.author,
        occurred_at=item.occurred_at,
        kind=item.kind.value,
    )
    try:
        report = extractor.extract(text, now)
    except ExtractionError as exc:
        item.extraction_error = str(exc)
        audit.record(
            db,
            actor="meow",
            action="extraction.failed",
            entity_type="source",
            entity_id=item.id,
            error=str(exc),
        )
        db.commit()
        raise
    item.extracted_at, item.extraction_error = utcnow(), None
    result.dropped = report.dropped
    for title, reason in report.dropped:
        audit.record(
            db,
            actor="meow",
            action="extraction.dropped",
            entity_type="source",
            entity_id=item.id,
            title=title,
            reason=reason,
        )
    for cand in report.candidates:
        result.proposals.append(
            proposals.propose(
                db,
                profile,
                ProposalKind.CREATE_TASK,
                cand.draft.model_dump(mode="json"),
                created_by="extractor",
                evidence=cand.evidence,
                confidence=cand.confidence,
                source_item_id=item.id,
            )
        )
    db.commit()
    return result


def capture_text(
    db: Session,
    profile: Profile,
    extractor: Extractor,
    body: str,
    *,
    title: str = "",
    now: datetime | None = None,
) -> CaptureResult:
    """The 'share to Meow' path: paste anything, get proposals back."""
    body = body.strip()
    if not body:
        raise ValueError("nothing to capture")
    item, created = store_source(
        db, kind=SourceKind.MANUAL, body=body, title=title.strip(), occurred_at=now or utcnow()
    )
    if not created and item.extracted_at is not None:
        existing = list(db.scalars(select(Proposal).where(Proposal.source_item_id == item.id)))
        return CaptureResult(source=item, proposals=existing, duplicate=True)
    return extract_into_proposals(db, profile, extractor, item, now or utcnow())


@dataclass(slots=True)
class ExtractionRun:
    processed: int = 0
    proposals: int = 0
    dropped: int = 0
    failed: int = 0
    error: str | None = None  # set when the run stopped early (e.g. Ollama is down)


def pending_extraction(db: Session, limit: int) -> list[SourceItem]:
    """Emails and Classroom announcements not yet read by the model, newest first.
    (Classroom coursework is structured, so it never needs the model.)"""
    stmt = (
        select(SourceItem)
        .where(
            SourceItem.extracted_at.is_(None),
            SourceItem.kind.in_([SourceKind.GMAIL, SourceKind.CLASSROOM]),
            SourceItem.external_id.not_like("coursework:%"),
        )
        .order_by(SourceItem.occurred_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def extract_pending(
    db: Session, profile: Profile, extractor: Extractor, now: datetime, limit: int
) -> ExtractionRun:
    run = ExtractionRun()
    for item in pending_extraction(db, limit):
        try:
            result = extract_into_proposals(db, profile, extractor, item, now)
        except ExtractionError as exc:
            run.failed += 1
            if "unreachable" in str(exc) or "not installed" in str(exc):
                run.error = str(exc)  # no point trying the rest right now
                break
            continue
        run.processed += 1
        run.proposals += len(result.proposals)
        run.dropped += len(result.dropped)
    return run
