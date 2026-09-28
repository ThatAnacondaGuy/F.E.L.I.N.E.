"""Turn the computed plan into focus-block proposals you can approve."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from meow.config import Profile
from meow.db.models import Proposal
from meow.domain.planner import Plan
from meow.domain.timeutil import utcnow
from meow.services import audit, proposals
from meow.services.tasks import build_plan
from meow.types import ProposalKind, ProposalStatus

LIVE = (ProposalStatus.PENDING, ProposalStatus.APPROVED, ProposalStatus.AUTO_APPROVED)


def _key(payload: dict[str, str]) -> tuple[str, str]:
    return payload["task_id"], payload["start_at"]


def propose_focus_blocks(
    db: Session, profile: Profile, now: datetime, *, within_hours: int = 36
) -> tuple[Plan, list[Proposal]]:
    """Propose the plan's sessions starting within ``within_hours``.

    Re-running is safe: sessions already proposed are skipped, and pending proposals the new
    plan no longer contains are marked superseded (which does not count against autonomy).
    """
    plan = build_plan(db, profile, now)
    cutoff = now + timedelta(hours=within_hours)
    wanted: dict[tuple[str, str], dict[str, str]] = {}
    for session in plan.sessions:
        if session.interval.start < cutoff:
            payload = proposals.FocusBlockDraft(
                task_id=session.task_id,
                start_at=session.interval.start,
                end_at=session.interval.end,
            ).model_dump(mode="json")
            wanted[_key(payload)] = payload

    live = list(
        db.scalars(
            select(Proposal).where(
                Proposal.kind == ProposalKind.SCHEDULE_FOCUS_BLOCK, Proposal.status.in_(LIVE)
            )
        )
    )
    for p in live:
        if p.status is ProposalStatus.PENDING and _key(p.payload) not in wanted:
            p.status, p.decided_at, p.decided_by = ProposalStatus.SUPERSEDED, utcnow(), "planner"
            audit.record(
                db,
                actor="planner",
                action="proposal.superseded",
                entity_type="proposal",
                entity_id=p.id,
            )
    db.commit()

    existing = {_key(p.payload) for p in live if p.status is not ProposalStatus.SUPERSEDED}
    created = [
        proposals.propose(
            db, profile, ProposalKind.SCHEDULE_FOCUS_BLOCK, payload, created_by="planner"
        )
        for key, payload in wanted.items()
        if key not in existing
    ]
    return plan, created
