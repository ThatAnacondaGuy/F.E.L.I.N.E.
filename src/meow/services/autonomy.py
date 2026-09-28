"""Earned autonomy: Meow gets more freedom per kind of action only by being right, measurably."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from meow.config import Profile
from meow.db.models import AutonomyLevelOverride, Proposal
from meow.domain.timeutil import utcnow
from meow.services import audit
from meow.types import AuthorityLevel, ProposalKind, ProposalStatus


class PromotionRefused(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AutonomyStatus:
    kind: ProposalKind
    level: AuthorityLevel
    most_autonomous: AuthorityLevel
    window: int  # decisions considered
    decisions: int
    accepted_clean: int
    accepted_edited: int
    rejected: int
    eligible: bool
    next_level: AuthorityLevel | None

    @property
    def acceptance(self) -> float:
        return self.accepted_clean / self.decisions if self.decisions else 0.0


def current_level(db: Session, profile: Profile, kind: ProposalKind) -> AuthorityLevel:
    override = db.get(AutonomyLevelOverride, kind)
    return override.level if override else profile.autonomy.kinds[kind].level


def status(db: Session, profile: Profile, kind: ProposalKind) -> AutonomyStatus:
    cfg = profile.autonomy
    ceiling = cfg.kinds[kind].most_autonomous
    level = current_level(db, profile, kind)
    # Only your own decisions count; auto-approved proposals are not evidence.
    recent = list(
        db.scalars(
            select(Proposal)
            .where(
                Proposal.kind == kind,
                Proposal.status.in_([ProposalStatus.APPROVED, ProposalStatus.REJECTED]),
            )
            .order_by(Proposal.decided_at.desc())
            .limit(cfg.promotion_min_decisions)
        )
    )
    clean = sum(1 for p in recent if p.status is ProposalStatus.APPROVED and not p.edited)
    edited = sum(1 for p in recent if p.status is ProposalStatus.APPROVED and p.edited)
    rejected = sum(1 for p in recent if p.status is ProposalStatus.REJECTED)
    decisions = len(recent)
    nxt = level.more_autonomous()
    eligible = (
        nxt is not None
        and nxt.rank >= ceiling.rank
        and decisions >= cfg.promotion_min_decisions
        and clean / decisions >= cfg.promotion_min_acceptance
    )
    return AutonomyStatus(
        kind=kind,
        level=level,
        most_autonomous=ceiling,
        window=cfg.promotion_min_decisions,
        decisions=decisions,
        accepted_clean=clean,
        accepted_edited=edited,
        rejected=rejected,
        eligible=eligible,
        next_level=nxt if eligible else None,
    )


def _set_level(db: Session, kind: ProposalKind, level: AuthorityLevel, reason: str) -> None:
    override = db.get(AutonomyLevelOverride, kind)
    if override is None:
        db.add(AutonomyLevelOverride(kind=kind, level=level, reason=reason))
    else:
        override.level, override.reason, override.changed_at = level, reason, utcnow()


def promote(
    db: Session, profile: Profile, kind: ProposalKind, *, actor: str = "user"
) -> AuthorityLevel:
    """One step more autonomous. Only you can do this, and only when the record supports it."""
    st = status(db, profile, kind)
    if not st.eligible or st.next_level is None:
        raise PromotionRefused(
            f"{kind.value} is not eligible: {st.accepted_clean}/{st.decisions} accepted unedited "
            f"(needs {profile.autonomy.promotion_min_decisions} decisions at "
            f"{profile.autonomy.promotion_min_acceptance:.0%}), ceiling {st.most_autonomous.value}"
        )
    reason = f"{st.accepted_clean}/{st.decisions} recent proposals accepted unedited"
    _set_level(db, kind, st.next_level, reason)
    audit.record(
        db,
        actor=actor,
        action="autonomy.promoted",
        entity_type="kind",
        entity_id=kind.value,
        authority_level=st.next_level,
        previous=st.level.value,
        reason=reason,
    )
    db.commit()
    return st.next_level


def demote_after_rejection(
    db: Session, profile: Profile, kind: ProposalKind
) -> AuthorityLevel | None:
    """A rejection while automatic drops the kind back to one-click (caller commits)."""
    level = current_level(db, profile, kind)
    if level is not AuthorityLevel.L1:
        return None
    new = AuthorityLevel.L2
    _set_level(db, kind, new, "rejected while automatic")
    audit.record(
        db,
        actor="system",
        action="autonomy.demoted",
        entity_type="kind",
        entity_id=kind.value,
        authority_level=new,
        previous=level.value,
    )
    return new
