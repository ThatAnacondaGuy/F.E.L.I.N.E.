"""Connected accounts: which account feeds which sources, and whether it needs attention."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from meow.db.models import ConnectedAccount, SyncState
from meow.domain.timeutil import utcnow
from meow.services import audit
from meow.types import SourceKind


class AccountNotFound(LookupError):
    pass


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError(f"not an email address: {email!r}")
    return email


def connect(
    db: Session, email: str, sources: Sequence[SourceKind], *, actor: str = "user"
) -> ConnectedAccount:
    """Record a successful sign-in (creating or updating the account)."""
    email = normalize_email(email)
    account = db.get(ConnectedAccount, email)
    if account is None:
        account = ConnectedAccount(email=email)
        db.add(account)
    account.sources = [s.value for s in sources]
    account.enabled = True
    account.needs_reauth = False
    account.last_error = None
    account.authorized_at = utcnow()
    audit.record(
        db,
        actor=actor,
        action="account.connected",
        entity_type="account",
        sources=account.sources,
        account=email,
    )
    db.commit()
    return account


def disconnect(db: Session, email: str, *, actor: str = "user") -> ConnectedAccount:
    account = get(db, email)
    account.enabled = False
    audit.record(
        db, actor=actor, action="account.disconnected", entity_type="account", account=account.email
    )
    db.commit()
    return account


def get(db: Session, email: str) -> ConnectedAccount:
    account = db.get(ConnectedAccount, normalize_email(email))
    if account is None:
        raise AccountNotFound(email)
    return account


def list_accounts(db: Session, *, enabled_only: bool = False) -> list[ConnectedAccount]:
    stmt = select(ConnectedAccount).order_by(ConnectedAccount.added_at)
    if enabled_only:
        stmt = stmt.where(ConnectedAccount.enabled.is_(True))
    return list(db.scalars(stmt))


def mark_needs_reauth(db: Session, account: ConnectedAccount, reason: str) -> None:
    """Flag the account (caller commits). Audited once, not on every retry."""
    if not account.needs_reauth:
        audit.record(
            db,
            actor="system",
            action="account.needs_reauth",
            entity_type="account",
            account=account.email,
            reason=reason,
        )
    account.needs_reauth = True
    account.last_error = reason


def sync_states(db: Session, email: str | None = None) -> list[SyncState]:
    stmt = select(SyncState).order_by(SyncState.account, SyncState.source)
    if email:
        stmt = stmt.where(SyncState.account == normalize_email(email))
    return list(db.scalars(stmt))
