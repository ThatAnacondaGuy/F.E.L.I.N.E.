from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from meow.config import Profile
from meow.db.models import AuditEntry, FocusSession, Task
from meow.services import autonomy, proposals, tasks
from meow.types import AuthorityLevel, ProposalKind, ProposalStatus

from support import ist

TASK = {
    "title": "Read the CUDA memory model chapter",
    "career_relevance": 0.9,
    "due_at": "2026-10-01T23:59:00+05:30",
    "estimated_minutes": 120,
}


def propose_task(db: Session, profile: Profile, **payload: Any) -> Any:
    return proposals.propose(
        db,
        profile,
        ProposalKind.CREATE_TASK,
        {**TASK, **payload},
        created_by="extractor",
        confidence=0.9,
        evidence="quote",
    )


def actions(db: Session) -> list[str]:
    return [e.action for e in db.query(AuditEntry).order_by(AuditEntry.id)]


def test_proposals_wait_for_approval(db: Session, profile: Profile) -> None:
    p = propose_task(db, profile)
    assert p.status is ProposalStatus.PENDING
    assert p.authority_level is AuthorityLevel.L2
    assert db.query(Task).count() == 0
    assert p.summary.startswith("Add task: Read the CUDA")


def test_approving_creates_the_task_with_provenance(db: Session, profile: Profile) -> None:
    p = propose_task(db, profile)
    proposals.approve(db, profile, p.id)
    task = db.get(Task, p.result_id)
    assert task is not None and task.proposal_id == p.id
    assert task.due_at == ist(2026, 10, 1, 23, 59)
    assert p.status is ProposalStatus.APPROVED and not p.edited
    assert actions(db) == ["proposal.created", "task.created", "proposal.approved"]


def test_edits_are_validated_applied_and_remembered(db: Session, profile: Profile) -> None:
    p = propose_task(db, profile)
    proposals.approve(db, profile, p.id, edits={"estimated_minutes": 60})
    assert p.edited
    assert db.get(Task, p.result_id).estimated_minutes == 60  # type: ignore[union-attr]


def test_same_instant_in_another_timezone_is_not_an_edit(db: Session, profile: Profile) -> None:
    p = propose_task(db, profile)
    proposals.approve(db, profile, p.id, edits={"due_at": "2026-10-01T18:29:00Z"})
    assert not p.edited


def test_invalid_edits_are_refused_and_nothing_changes(db: Session, profile: Profile) -> None:
    p = propose_task(db, profile)
    with pytest.raises(proposals.ProposalError):
        proposals.approve(db, profile, p.id, edits={"estimated_minutes": -5})
    db.rollback()
    assert proposals.get_proposal(db, p.id).status is ProposalStatus.PENDING
    assert db.query(Task).count() == 0


def test_invalid_payloads_never_become_proposals(db: Session, profile: Profile) -> None:
    with pytest.raises(proposals.ProposalError):
        propose_task(db, profile, due_at="2026-10-01T23:59")  # naive: no timezone


def test_decisions_are_final(db: Session, profile: Profile) -> None:
    p = propose_task(db, profile)
    proposals.reject(db, profile, p.id, reason="not mine")
    with pytest.raises(proposals.ProposalError, match="already rejected"):
        proposals.approve(db, profile, p.id)


def test_focus_block_proposal_creates_a_session(db: Session, profile: Profile) -> None:
    task = tasks.add_task(db, tasks.TaskDraft(title="CUDA reduction kernel"))
    p = proposals.propose(
        db,
        profile,
        ProposalKind.SCHEDULE_FOCUS_BLOCK,
        {
            "task_id": task.id,
            "start_at": ist(2026, 9, 28, 16, 30).isoformat(),
            "end_at": ist(2026, 9, 28, 19, 0).isoformat(),
        },
        created_by="planner",
    )
    assert "CUDA reduction kernel" in p.summary and "16:30–19:00" in p.summary
    proposals.approve(db, profile, p.id)
    session = db.get(FocusSession, p.result_id)
    assert session is not None and session.task_id == task.id


# ── earned autonomy ──────────────────────────────────────────────────────


def decide(db: Session, profile: Profile, approve: int, reject: int = 0, edit: int = 0) -> None:
    for i in range(approve + reject + edit):
        p = propose_task(db, profile, title=f"Task {i}")
        if i < approve:
            proposals.approve(db, profile, p.id)
        elif i < approve + edit:
            proposals.approve(db, profile, p.id, edits={"estimated_minutes": 5})
        else:
            proposals.reject(db, profile, p.id)


def test_promotion_needs_a_track_record(db: Session, profile: Profile) -> None:
    decide(db, profile, approve=19)
    status = autonomy.status(db, profile, ProposalKind.CREATE_TASK)
    assert not status.eligible
    with pytest.raises(autonomy.PromotionRefused):
        autonomy.promote(db, profile, ProposalKind.CREATE_TASK)


def test_edits_count_against_promotion(db: Session, profile: Profile) -> None:
    decide(db, profile, approve=18, edit=2)
    status = autonomy.status(db, profile, ProposalKind.CREATE_TASK)
    assert status.decisions == 20 and status.acceptance == 0.9
    assert not status.eligible


def test_earned_promotion_then_auto_approval_then_demotion(db: Session, profile: Profile) -> None:
    decide(db, profile, approve=20)
    assert autonomy.promote(db, profile, ProposalKind.CREATE_TASK) is AuthorityLevel.L1

    confident = propose_task(db, profile, title="Auto")
    assert confident.status is ProposalStatus.AUTO_APPROVED
    assert db.get(Task, confident.result_id) is not None

    unsure = proposals.propose(
        db,
        profile,
        ProposalKind.CREATE_TASK,
        {**TASK, "title": "Unsure"},
        created_by="extractor",
        confidence=0.5,
    )
    assert unsure.status is ProposalStatus.PENDING  # low confidence still asks

    proposals.reject(db, profile, unsure.id, reason="wrong")
    assert autonomy.current_level(db, profile, ProposalKind.CREATE_TASK) is AuthorityLevel.L2
    assert "autonomy.demoted" in actions(db)


def test_auto_approvals_are_not_counted_as_your_decisions(db: Session, profile: Profile) -> None:
    decide(db, profile, approve=20)
    autonomy.promote(db, profile, ProposalKind.CREATE_TASK)
    before = autonomy.status(db, profile, ProposalKind.CREATE_TASK)
    propose_task(db, profile, title="Auto")
    after = autonomy.status(db, profile, ProposalKind.CREATE_TASK)
    assert (before.decisions, before.accepted_clean) == (after.decisions, after.accepted_clean)


def test_ceiling_blocks_promotion(db: Session, profile: Profile) -> None:
    kinds = dict(profile.autonomy.kinds)
    kinds[ProposalKind.CREATE_TASK] = kinds[ProposalKind.CREATE_TASK].model_copy(
        update={"most_autonomous": AuthorityLevel.L2}
    )
    capped = profile.model_copy(
        update={"autonomy": profile.autonomy.model_copy(update={"kinds": kinds})}
    )
    decide(db, capped, approve=20)
    assert not autonomy.status(db, capped, ProposalKind.CREATE_TASK).eligible
