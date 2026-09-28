from __future__ import annotations

from sqlalchemy.orm import Session

from meow.config import Profile
from meow.db.models import CalendarEvent, FocusSession, Proposal
from meow.services import planning, proposals, tasks
from meow.types import ProposalKind, ProposalStatus

from support import ist

NOW = ist(2026, 9, 28, 16, 0)


def add(db: Session, title: str, minutes: int, **kw: object) -> str:
    return tasks.add_task(db, tasks.TaskDraft(title=title, estimated_minutes=minutes, **kw)).id  # type: ignore[arg-type]


def test_plan_avoids_calendar_events(db: Session, profile: Profile) -> None:
    add(db, "Essay", 60)
    db.add(
        CalendarEvent(
            external_id="e1",
            title="CSI meeting",
            start_at=ist(2026, 9, 28, 16, 30),
            end_at=ist(2026, 9, 28, 17, 30),
        )
    )
    db.commit()
    plan = tasks.build_plan(db, profile, NOW)
    assert plan.sessions[0].interval.start == ist(2026, 9, 28, 17, 45)


def test_proposing_twice_does_not_duplicate(db: Session, profile: Profile) -> None:
    add(db, "Essay", 60)
    _, first = planning.propose_focus_blocks(db, profile, NOW)
    _, second = planning.propose_focus_blocks(db, profile, NOW)
    assert len(first) == 1 and second == []


def test_approved_blocks_count_as_progress(db: Session, profile: Profile) -> None:
    add(db, "Big report", 300)
    _, created = planning.propose_focus_blocks(db, profile, NOW)
    for p in created:
        proposals.approve(db, profile, p.id)
    plan = tasks.build_plan(db, profile, NOW)
    assert plan.sessions == ()  # all 300 minutes are booked; nothing left to plan
    _, again = planning.propose_focus_blocks(db, profile, NOW)
    assert again == []


def test_stale_pending_blocks_are_superseded_not_rejected(db: Session, profile: Profile) -> None:
    add(db, "Essay", 60)
    _, (old,) = planning.propose_focus_blocks(db, profile, NOW)
    # A higher-priority task arrives and takes the 16:30 slot.
    add(db, "Urgent lab", 60, importance="critical", due_at=ist(2026, 9, 28, 20, 0))
    _, created = planning.propose_focus_blocks(db, profile, NOW)
    db.refresh(old)
    assert old.status is ProposalStatus.SUPERSEDED
    assert len(created) == 2
    rejected = db.query(Proposal).filter_by(status=ProposalStatus.REJECTED).count()
    assert rejected == 0
    assert all(p.kind is ProposalKind.SCHEDULE_FOCUS_BLOCK for p in created)


def test_inbox_lists_new_tasks_first_then_blocks_in_time_order(
    db: Session, profile: Profile
) -> None:
    add(db, "Big report", 300)
    planning.propose_focus_blocks(db, profile, NOW)
    proposals.propose(
        db, profile, ProposalKind.CREATE_TASK, {"title": "New one"}, created_by="extractor"
    )
    ordered = proposals.inbox_order(proposals.list_proposals(db))
    assert ordered[0].kind is ProposalKind.CREATE_TASK
    starts = [p.payload["start_at"] for p in ordered[1:]]
    assert starts == sorted(starts) and len(starts) == 2


def test_approve_all_focus_blocks(db: Session, profile: Profile) -> None:
    add(db, "Big report", 300)
    planning.propose_focus_blocks(db, profile, NOW)
    approved = proposals.approve_all(db, profile, ProposalKind.SCHEDULE_FOCUS_BLOCK)
    assert len(approved) == 2
    assert all(p.status is ProposalStatus.APPROVED for p in approved)
    assert db.query(FocusSession).count() == 2


def test_focus_blocks_whose_time_passed_expire(db: Session, profile: Profile) -> None:
    from meow.services import autonomy

    add(db, "Essay", 60)
    _, (block,) = planning.propose_focus_blocks(db, profile, NOW)  # 16:30-17:30
    assert proposals.expire_stale(db, ist(2026, 9, 28, 16, 0)) == 0
    assert proposals.expire_stale(db, ist(2026, 9, 28, 16, 31)) == 1
    db.refresh(block)
    assert block.status is ProposalStatus.EXPIRED
    status = autonomy.status(db, profile, ProposalKind.SCHEDULE_FOCUS_BLOCK)
    assert status.decisions == 0 and status.rejected == 0  # not held against Meow
