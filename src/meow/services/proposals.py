"""Proposals: everything Meow wants to do waits here for a decision.

L1 kinds with high enough confidence apply immediately (and are recorded as auto-approved);
everything else is pending until you approve, edit-and-approve, or reject it.
"""

from __future__ import annotations

from typing import Any, Self
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from meow.config import Profile
from meow.db.models import FocusSession, Proposal
from meow.domain.timeutil import utcnow
from meow.services import audit, autonomy
from meow.services.tasks import TaskDraft, create_task, get_task
from meow.types import AuthorityLevel, ProposalKind, ProposalStatus


class FocusBlockDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


PAYLOAD_MODELS: dict[ProposalKind, type[BaseModel]] = {
    ProposalKind.CREATE_TASK: TaskDraft,
    ProposalKind.SCHEDULE_FOCUS_BLOCK: FocusBlockDraft,
}


class ProposalError(ValueError):
    pass


class ProposalNotFound(LookupError):
    pass


def _validate(kind: ProposalKind, payload: dict[str, Any]) -> BaseModel:
    try:
        return PAYLOAD_MODELS[kind].model_validate(payload)
    except ValidationError as exc:
        raise ProposalError(f"invalid {kind.value} payload: {exc}") from exc


def _summary(db: Session, draft: BaseModel, tz: ZoneInfo) -> str:
    if isinstance(draft, TaskDraft):
        due = f" (due {draft.due_at.astimezone(tz):%a %d %b %H:%M})" if draft.due_at else ""
        return f"Add task: {draft.title}{due}"
    if isinstance(draft, FocusBlockDraft):
        task = get_task(db, draft.task_id)
        start, end = draft.start_at.astimezone(tz), draft.end_at.astimezone(tz)
        return f"Focus on “{task.title}” {start:%a %d %b %H:%M}–{end:%H:%M}"
    raise TypeError(type(draft))


def _apply(db: Session, proposal: Proposal, draft: BaseModel, actor: str) -> str:
    if isinstance(draft, TaskDraft):
        task = create_task(
            db, draft, actor=actor, source_item_id=proposal.source_item_id, proposal_id=proposal.id
        )
        return task.id
    if isinstance(draft, FocusBlockDraft):
        get_task(db, draft.task_id)
        session = FocusSession(
            task_id=draft.task_id,
            start_at=draft.start_at,
            end_at=draft.end_at,
            proposal_id=proposal.id,
        )
        db.add(session)
        db.flush()
        audit.record(
            db,
            actor=actor,
            action="focus_session.created",
            entity_type="focus_session",
            entity_id=session.id,
            task_id=draft.task_id,
        )
        return session.id
    raise TypeError(type(draft))


def propose(
    db: Session,
    profile: Profile,
    kind: ProposalKind,
    payload: dict[str, Any],
    *,
    created_by: str,
    evidence: str | None = None,
    confidence: float = 1.0,
    source_item_id: str | None = None,
) -> Proposal:
    draft = _validate(kind, payload)
    level = autonomy.current_level(db, profile, kind)
    proposal = Proposal(
        kind=kind,
        payload=draft.model_dump(mode="json"),
        summary=_summary(db, draft, profile.user.tz),
        evidence=evidence,
        confidence=confidence,
        authority_level=level,
        source_item_id=source_item_id,
        created_by=created_by,
    )
    db.add(proposal)
    db.flush()
    audit.record(
        db,
        actor=created_by,
        action="proposal.created",
        entity_type="proposal",
        entity_id=proposal.id,
        authority_level=level,
        kind=kind.value,
        confidence=confidence,
        summary=proposal.summary,
    )
    auto = level is AuthorityLevel.L1 and confidence >= profile.autonomy.auto_approve_min_confidence
    if auto:
        proposal.result_id = _apply(db, proposal, draft, actor="meow")
        proposal.status = ProposalStatus.AUTO_APPROVED
        proposal.decided_at, proposal.decided_by = utcnow(), "meow"
        audit.record(
            db,
            actor="meow",
            action="proposal.auto_approved",
            entity_type="proposal",
            entity_id=proposal.id,
            authority_level=level,
        )
    db.commit()
    return proposal


def get_proposal(db: Session, proposal_id: str) -> Proposal:
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise ProposalNotFound(proposal_id)
    return proposal


def _pending(db: Session, proposal_id: str) -> Proposal:
    proposal = get_proposal(db, proposal_id)
    if proposal.status is not ProposalStatus.PENDING:
        raise ProposalError(f"proposal is already {proposal.status.value}")
    return proposal


def approve(
    db: Session,
    profile: Profile,
    proposal_id: str,
    *,
    edits: dict[str, Any] | None = None,
    actor: str = "user",
) -> Proposal:
    proposal = _pending(db, proposal_id)
    original = _validate(proposal.kind, proposal.payload)
    draft = _validate(proposal.kind, {**proposal.payload, **(edits or {})})
    edited = draft != original  # compares values, so the same instant in another tz is no edit
    proposal.result_id = _apply(db, proposal, draft, actor=actor)
    proposal.payload = draft.model_dump(mode="json")
    proposal.status = ProposalStatus.APPROVED
    proposal.edited = edited
    proposal.decided_at, proposal.decided_by = utcnow(), actor
    audit.record(
        db,
        actor=actor,
        action="proposal.approved",
        entity_type="proposal",
        entity_id=proposal.id,
        authority_level=proposal.authority_level,
        edited=edited,
    )
    db.commit()
    return proposal


def reject(
    db: Session, profile: Profile, proposal_id: str, *, reason: str = "", actor: str = "user"
) -> Proposal:
    proposal = _pending(db, proposal_id)
    proposal.status = ProposalStatus.REJECTED
    proposal.decision_note = reason or None
    proposal.decided_at, proposal.decided_by = utcnow(), actor
    audit.record(
        db,
        actor=actor,
        action="proposal.rejected",
        entity_type="proposal",
        entity_id=proposal.id,
        authority_level=proposal.authority_level,
        reason=reason,
    )
    autonomy.demote_after_rejection(db, profile, proposal.kind)
    db.commit()
    return proposal


def list_proposals(
    db: Session, status: ProposalStatus | None = ProposalStatus.PENDING, limit: int = 200
) -> list[Proposal]:
    stmt = select(Proposal).order_by(Proposal.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Proposal.status == status)
    return list(db.scalars(stmt))


def inbox_order(pending: list[Proposal]) -> list[Proposal]:
    """New tasks first (newest on top), then focus blocks in the order they happen."""
    tasks_first = [p for p in pending if p.kind is ProposalKind.CREATE_TASK]
    blocks = sorted(
        (p for p in pending if p.kind is ProposalKind.SCHEDULE_FOCUS_BLOCK),
        key=lambda p: str(p.payload.get("start_at", "")),
    )
    others = [p for p in pending if p not in tasks_first and p not in blocks]
    return tasks_first + blocks + others


def approve_all(
    db: Session, profile: Profile, kind: ProposalKind, *, actor: str = "user"
) -> list[Proposal]:
    """Approve every pending proposal of one kind (each is recorded as your decision)."""
    pending = [p for p in list_proposals(db, ProposalStatus.PENDING) if p.kind is kind]
    return [approve(db, profile, p.id, actor=actor) for p in pending]
