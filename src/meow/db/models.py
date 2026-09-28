"""The data model. This file is the single source of truth for the schema;
migrations are checked against it in the test suite."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, ClassVar

from sqlalchemy import JSON, Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from meow.db.coltypes import StrEnumType, UTCDateTime
from meow.domain.timeutil import utcnow
from meow.types import (
    AuthorityLevel,
    Category,
    Importance,
    ProposalKind,
    ProposalStatus,
    SourceKind,
    TaskStatus,
)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: UTCDateTime(),
        dict[str, Any]: JSON(),
    }


class SourceItem(Base):
    """A raw piece of input (an email, a Classroom post, pasted text) kept for provenance."""

    __tablename__ = "source_items"
    __table_args__ = (UniqueConstraint("kind", "account", "external_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[SourceKind] = mapped_column(StrEnumType(SourceKind))
    account: Mapped[str] = mapped_column(String(320), default="")
    external_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str | None] = mapped_column(String(320))
    url: Mapped[str | None] = mapped_column(String(2048))
    occurred_at: Mapped[datetime | None]
    content_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(default=utcnow)
    extracted_at: Mapped[datetime | None]
    extraction_error: Mapped[str | None] = mapped_column(Text)


class Proposal(Base):
    """Something Meow wants to do. Nothing takes effect until it is approved."""

    __tablename__ = "proposals"
    __table_args__ = (Index("ix_proposals_kind_status", "kind", "status"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[ProposalKind] = mapped_column(StrEnumType(ProposalKind))
    status: Mapped[ProposalStatus] = mapped_column(
        StrEnumType(ProposalStatus), default=ProposalStatus.PENDING
    )
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    summary: Mapped[str] = mapped_column(String(500), default="")
    evidence: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    authority_level: Mapped[AuthorityLevel] = mapped_column(StrEnumType(AuthorityLevel))
    source_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_items.id", ondelete="SET NULL"), index=True
    )
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    decided_at: Mapped[datetime | None]
    decided_by: Mapped[str | None] = mapped_column(String(64))
    decision_note: Mapped[str | None] = mapped_column(Text)
    edited: Mapped[bool] = mapped_column(default=False)
    result_id: Mapped[str | None] = mapped_column(String(32))

    source_item: Mapped[SourceItem | None] = relationship()


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[TaskStatus] = mapped_column(
        StrEnumType(TaskStatus), default=TaskStatus.TODO, index=True
    )
    importance: Mapped[Importance] = mapped_column(
        StrEnumType(Importance), default=Importance.MEDIUM
    )
    category: Mapped[Category] = mapped_column(StrEnumType(Category), default=Category.PERSONAL)
    due_at: Mapped[datetime | None] = mapped_column(index=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    course_code: Mapped[str | None] = mapped_column(String(32))
    career_relevance: Mapped[float] = mapped_column(Float, default=0.0)
    source_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_items.id", ondelete="SET NULL")
    )
    proposal_id: Mapped[str | None] = mapped_column(ForeignKey("proposals.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None]

    source_item: Mapped[SourceItem | None] = relationship()


class CalendarEvent(Base):
    """Busy time from your calendars. The planner schedules around these."""

    __tablename__ = "calendar_events"
    __table_args__ = (UniqueConstraint("account", "calendar_id", "external_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    account: Mapped[str] = mapped_column(String(320), default="")
    calendar_id: Mapped[str] = mapped_column(String(255), default="")
    external_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500), default="")
    start_at: Mapped[datetime] = mapped_column(index=True)
    end_at: Mapped[datetime]
    all_day: Mapped[bool] = mapped_column(default=False)
    busy: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class FocusSession(Base):
    """An approved block of planned work on a task."""

    __tablename__ = "focus_sessions"
    __table_args__ = (UniqueConstraint("task_id", "start_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    start_at: Mapped[datetime] = mapped_column(index=True)
    end_at: Mapped[datetime]
    proposal_id: Mapped[str | None] = mapped_column(ForeignKey("proposals.id", ondelete="SET NULL"))
    calendar_event_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    task: Mapped[Task] = relationship()


class AutonomyLevelOverride(Base):
    """The current level for a kind of action once it has been promoted or demoted."""

    __tablename__ = "autonomy_levels"

    kind: Mapped[ProposalKind] = mapped_column(StrEnumType(ProposalKind), primary_key=True)
    level: Mapped[AuthorityLevel] = mapped_column(StrEnumType(AuthorityLevel))
    changed_at: Mapped[datetime] = mapped_column(default=utcnow)
    reason: Mapped[str] = mapped_column(Text, default="")


class AuditEntry(Base):
    """Append-only record of everything Meow and you did."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(32))
    authority_level: Mapped[AuthorityLevel | None] = mapped_column(StrEnumType(AuthorityLevel))
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)


class ConnectedAccount(Base):
    """An external account Meow reads from. Its OAuth token lives in the Keychain, not here."""

    __tablename__ = "connected_accounts"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="google")
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(default=True)
    needs_reauth: Mapped[bool] = mapped_column(default=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(default=utcnow)
    authorized_at: Mapped[datetime | None]
    focus_calendar_id: Mapped[str | None] = mapped_column(String(255))


class SyncState(Base):
    """Progress and health of one source for one account."""

    __tablename__ = "sync_state"
    __table_args__ = (UniqueConstraint("source", "account"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source: Mapped[SourceKind] = mapped_column(StrEnumType(SourceKind))
    account: Mapped[str] = mapped_column(String(320))
    cursor: Mapped[str | None] = mapped_column(String(255))
    last_attempt_at: Mapped[datetime | None]
    last_success_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    items_new: Mapped[int] = mapped_column(Integer, default=0)


class Briefing(Base):
    """A morning or evening briefing. One of each per day."""

    __tablename__ = "briefings"
    __table_args__ = (UniqueConstraint("kind", "day"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))
    day: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    headline: Mapped[str] = mapped_column(String(300))
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    notified: Mapped[bool] = mapped_column(default=False)
