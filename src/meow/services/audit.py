from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from meow.db.models import AuditEntry
from meow.types import AuthorityLevel


def record(
    db: Session,
    *,
    actor: str,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    authority_level: AuthorityLevel | None = None,
    **detail: Any,
) -> AuditEntry:
    """Append an audit entry to the current transaction (the caller commits)."""
    entry = AuditEntry(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        authority_level=authority_level,
        detail=detail,
    )
    db.add(entry)
    return entry


def recent(db: Session, limit: int = 100) -> list[AuditEntry]:
    stmt = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)
    return list(db.scalars(stmt))
