"""Response models for the JSON API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from meow.db.models import AuditEntry, Briefing, Proposal, Task
from meow.domain.planner import Plan
from meow.domain.prioritizer import Score
from meow.services.autonomy import AutonomyStatus
from meow.services.syncing import FullSync
from meow.types import (
    AuthorityLevel,
    Category,
    Importance,
    ProposalKind,
    ProposalStatus,
    SourceKind,
    TaskStatus,
)


class FactorOut(BaseModel):
    name: str
    value: float
    weight: float
    points: float
    reason: str


class ScoreOut(BaseModel):
    total: float
    reasons: list[str]
    factors: list[FactorOut]

    @classmethod
    def of(cls, score: Score) -> ScoreOut:
        return cls(
            total=score.total,
            reasons=score.top_reasons(),
            factors=[
                FactorOut(
                    name=f.name,
                    value=round(f.value, 3),
                    weight=f.weight,
                    points=round(f.points, 1),
                    reason=f.reason,
                )
                for f in score.factors
            ],
        )


class TaskOut(BaseModel):
    id: str
    title: str
    notes: str
    status: TaskStatus
    importance: Importance
    category: Category
    due_at: datetime | None
    estimated_minutes: int | None
    course_code: str | None
    career_relevance: float
    created_at: datetime
    score: ScoreOut | None = None

    @classmethod
    def of(cls, task: Task, score: Score | None = None) -> TaskOut:
        return cls(
            id=task.id,
            title=task.title,
            notes=task.notes,
            status=task.status,
            importance=task.importance,
            category=task.category,
            due_at=task.due_at,
            estimated_minutes=task.estimated_minutes,
            course_code=task.course_code,
            career_relevance=task.career_relevance,
            created_at=task.created_at,
            score=ScoreOut.of(score) if score else None,
        )


class ProposalOut(BaseModel):
    id: str
    kind: ProposalKind
    status: ProposalStatus
    summary: str
    payload: dict[str, Any]
    evidence: str | None
    confidence: float
    authority_level: AuthorityLevel
    source_item_id: str | None
    created_by: str
    created_at: datetime
    decided_at: datetime | None
    edited: bool
    result_id: str | None

    @classmethod
    def of(cls, p: Proposal) -> ProposalOut:
        return cls(
            id=p.id,
            kind=p.kind,
            status=p.status,
            summary=p.summary,
            payload=p.payload,
            evidence=p.evidence,
            confidence=p.confidence,
            authority_level=p.authority_level,
            source_item_id=p.source_item_id,
            created_by=p.created_by,
            created_at=p.created_at,
            decided_at=p.decided_at,
            edited=p.edited,
            result_id=p.result_id,
        )


class ApproveIn(BaseModel):
    edits: dict[str, Any] | None = None


class RejectIn(BaseModel):
    reason: str = Field(default="", max_length=1000)


class CaptureIn(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    title: str = Field(default="", max_length=500)


class CaptureOut(BaseModel):
    source_id: str
    duplicate: bool
    proposals: list[ProposalOut]
    dropped: list[dict[str, str]]


class SessionOut(BaseModel):
    task_id: str
    title: str
    start_at: datetime
    end_at: datetime
    day: str


class ShortfallOut(BaseModel):
    task_id: str
    title: str
    missing_minutes: int
    at_risk: bool
    reason: str


class PlanOut(BaseModel):
    horizon_start: datetime
    horizon_end: datetime
    sessions: list[SessionOut]
    shortfalls: list[ShortfallOut]

    @classmethod
    def of(cls, plan: Plan) -> PlanOut:
        return cls(
            horizon_start=plan.horizon.start,
            horizon_end=plan.horizon.end,
            sessions=[
                SessionOut(
                    task_id=s.task_id,
                    title=s.title,
                    start_at=s.interval.start,
                    end_at=s.interval.end,
                    day=s.day.isoformat(),
                )
                for s in plan.sessions
            ],
            shortfalls=[
                ShortfallOut(
                    task_id=s.task_id,
                    title=s.title,
                    missing_minutes=s.missing_minutes,
                    at_risk=s.at_risk,
                    reason=s.reason,
                )
                for s in plan.shortfalls
            ],
        )


class AutonomyOut(BaseModel):
    kind: ProposalKind
    level: AuthorityLevel
    most_autonomous: AuthorityLevel
    decisions: int
    window: int
    accepted_clean: int
    accepted_edited: int
    rejected: int
    acceptance: float
    eligible: bool
    next_level: AuthorityLevel | None

    @classmethod
    def of(cls, s: AutonomyStatus) -> AutonomyOut:
        return cls(
            kind=s.kind,
            level=s.level,
            most_autonomous=s.most_autonomous,
            decisions=s.decisions,
            window=s.window,
            accepted_clean=s.accepted_clean,
            accepted_edited=s.accepted_edited,
            rejected=s.rejected,
            acceptance=round(s.acceptance, 3),
            eligible=s.eligible,
            next_level=s.next_level,
        )


class AuditOut(BaseModel):
    id: int
    at: datetime
    actor: str
    action: str
    entity_type: str | None
    entity_id: str | None
    authority_level: AuthorityLevel | None
    detail: dict[str, Any]

    @classmethod
    def of(cls, e: AuditEntry) -> AuditOut:
        return cls(
            id=e.id,
            at=e.at,
            actor=e.actor,
            action=e.action,
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            authority_level=e.authority_level,
            detail=e.detail,
        )


class SyncStateOut(BaseModel):
    source: SourceKind
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None
    items_new: int


class AccountOut(BaseModel):
    email: str
    sources: list[str]
    enabled: bool
    needs_reauth: bool
    last_error: str | None
    authorized_at: datetime | None
    sync: list[SyncStateOut]


class SyncResultOut(BaseModel):
    account: str
    source: SourceKind
    new_items: int
    proposals: int
    pushed: int
    removed: int
    error: str | None


class SyncRunOut(BaseModel):
    results: list[SyncResultOut]
    reauth_needed: list[str]
    extracted: int
    extraction_proposals: int
    extraction_error: str | None

    @classmethod
    def of(cls, run: FullSync) -> SyncRunOut:
        return cls(
            results=[
                SyncResultOut(
                    account=r.account,
                    source=r.source,
                    new_items=r.new_items,
                    proposals=r.proposals,
                    pushed=r.pushed,
                    removed=r.removed,
                    error=r.error,
                )
                for r in run.google.results
            ],
            reauth_needed=run.google.reauth_needed,
            extracted=run.extraction.processed,
            extraction_proposals=run.extraction.proposals,
            extraction_error=run.extraction.error,
        )


class BriefingSectionOut(BaseModel):
    heading: str
    items: list[str]
    tone: str = ""


class BriefingOut(BaseModel):
    kind: str
    day: date
    created_at: datetime
    headline: str
    sections: list[BriefingSectionOut]
    notified: bool

    @classmethod
    def of(cls, b: Briefing) -> BriefingOut:
        return cls(
            kind=b.kind,
            day=b.day,
            created_at=b.created_at,
            headline=b.headline,
            sections=[BriefingSectionOut(**x) for x in b.sections],
            notified=b.notified,
        )
