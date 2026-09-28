from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from meow.config import Profile, Settings
from meow.db.engine import make_session_factory
from meow.db.models import Briefing
from meow.notify import MacNotifier
from meow.services import accounts, briefings, planning, proposals, tasks
from meow.services.background import BriefingJob, SyncJob, Worker
from meow.types import BriefingKind, Importance, ProposalKind, SourceKind, TaskStatus

from support import RecordingNotifier, ist

MORNING = ist(2026, 9, 28, 8, 15)  # a Monday


def add(db: Session, title: str, **kw: object) -> str:
    return tasks.add_task(db, tasks.TaskDraft(title=title, **kw)).id  # type: ignore[arg-type]


def sections(draft: briefings.Draft) -> dict[str, list[str]]:
    return {s.heading: s.items for s in draft.sections}


# ── content ──────────────────────────────────────────────────────────────


def test_morning_briefing_covers_the_day(db: Session, profile: Profile) -> None:
    add(
        db,
        "AI assignment 2",
        due_at=ist(2026, 9, 29, 23, 59),
        estimated_minutes=120,
        course_code="PCC301COM",
        importance=Importance.HIGH,
    )
    add(db, "Seminar draft", due_at=ist(2026, 10, 5, 23, 59))
    planning.propose_focus_blocks(db, profile, MORNING)
    proposals.approve_all(db, profile, ProposalKind.SCHEDULE_FOCUS_BLOCK)
    draft = briefings.compose(db, profile, BriefingKind.MORNING, MORNING)
    got = sections(draft)
    assert got["Today"][:3] == [
        "08:00–09:15 Morning routine",
        "09:15–16:30 College",
        "16:30–04:00 Deep focus",
    ]
    assert got["Focus blocks"][0] == "16:30–18:30 AI assignment 2"
    assert got["Due in the next 48 hours"] == ["AI assignment 2: Tue 23:59 (in 1d 15h)"]
    assert got["Top priorities"][0].startswith("AI assignment 2 (")
    assert draft.headline.startswith("2 focus blocks today · 1 due in 48h")


def test_morning_without_approved_blocks_points_to_the_inbox(db: Session, profile: Profile) -> None:
    add(db, "Essay", estimated_minutes=60)
    got = sections(briefings.compose(db, profile, BriefingKind.MORNING, MORNING))
    assert got["Focus blocks"] == [
        "None approved yet. The planner suggests 1 block — open Meow to review them."
    ]


def test_clear_day_says_so(db: Session, profile: Profile) -> None:
    draft = briefings.compose(db, profile, BriefingKind.MORNING, MORNING)
    assert draft.headline == "A clear day: nothing due in the next 48 hours."


def test_evening_briefing_reviews_the_day(db: Session, profile: Profile) -> None:
    evening = ist(2026, 9, 28, 22, 0)
    done = add(db, "Read CUDA chapter 3")
    tasks.set_status(db, done, TaskStatus.DONE, actor="user", now=ist(2026, 9, 28, 19, 0))
    add(db, "Submit CN lab", due_at=ist(2026, 9, 29, 17, 0))
    add(db, "Later thing", due_at=ist(2026, 10, 9, 17, 0))
    accounts.connect(db, "me@gmail.test", [SourceKind.GMAIL])
    acct = accounts.get(db, "me@gmail.test")
    accounts.mark_needs_reauth(db, acct, "expired")
    db.commit()
    draft = briefings.compose(db, profile, BriefingKind.EVENING, evening)
    got = sections(draft)
    assert got["Done today"] == ["Read CUDA chapter 3"]
    assert got["Due by tomorrow"] == ["Submit CN lab: Tue 17:00 (in 19h)"]
    assert "Sign in again: meow google login me@gmail.test" in got["Waiting for you"]
    assert draft.headline.startswith("1 done today")


def test_at_risk_work_is_flagged(db: Session, profile: Profile) -> None:
    add(db, "Huge report", due_at=MORNING + timedelta(hours=10), estimated_minutes=600)
    draft = briefings.compose(db, profile, BriefingKind.MORNING, MORNING)
    risk = next(s for s in draft.sections if s.heading == "At risk")
    assert risk.tone == "risk" and "Huge report" in risk.items[0]


# ── generation, dedupe, notifications ────────────────────────────────────


def test_one_briefing_per_kind_per_day(db: Session, profile: Profile) -> None:
    notifier = RecordingNotifier()
    first = briefings.generate(db, profile, BriefingKind.MORNING, MORNING, notifier)
    again = briefings.generate(db, profile, BriefingKind.MORNING, MORNING, notifier)
    assert first.id == again.id and db.query(Briefing).count() == 1
    assert notifier.sent == [("Meow · Morning briefing", first.headline)]


def test_no_notifications_during_quiet_hours(db: Session, profile: Profile) -> None:
    notifier = RecordingNotifier()
    row = briefings.generate(db, profile, BriefingKind.MORNING, ist(2026, 9, 28, 5, 0), notifier)
    assert notifier.sent == [] and not row.notified


def test_mac_notifier_passes_text_as_arguments_not_code() -> None:
    calls: list[list[str]] = []
    notifier = MacNotifier(runner=lambda args: calls.append(list(args)) or 0)
    evil = 'done" & do shell script "rm -rf ~" & "'
    cmd = notifier.command("Meow", evil)
    assert cmd[-1] == evil  # the hostile text is an argv item...
    assert all(evil not in part for part in cmd[:-1])  # ...and appears in no script line


# ── background worker ────────────────────────────────────────────────────


def test_briefing_job_fires_once_inside_its_window(settings: Settings, db: Session) -> None:
    notifier = RecordingNotifier()
    job = BriefingJob(settings, notifier)
    sessions = make_session_factory(db.get_bind())  # type: ignore[arg-type]
    assert not job.due(ist(2026, 9, 28, 8, 0))  # before 08:15
    assert job.due(MORNING)
    job.run(sessions, MORNING)
    assert not job.due(ist(2026, 9, 28, 8, 45))  # already done today
    assert len(notifier.sent) == 1
    assert not job.due(ist(2026, 9, 28, 11, 30))  # outside the 3h grace window anyway


def test_late_start_skips_the_morning_briefing(settings: Settings) -> None:
    job = BriefingJob(settings, RecordingNotifier())
    assert job.pending(ist(2026, 9, 28, 15, 0)) == []  # Meow started mid-afternoon
    assert job.pending(ist(2026, 9, 28, 22, 5)) == [BriefingKind.EVENING]


def test_nudge_makes_sync_due_immediately(settings: Settings, db: Session) -> None:
    job = SyncJob(settings, llm_factory=None)
    job.last_run = MORNING
    assert not job.due(MORNING + timedelta(minutes=1))
    worker = Worker(make_session_factory(db.get_bind()), [job])  # type: ignore[arg-type]
    worker.nudge_sync()
    assert job.due(MORNING + timedelta(minutes=1))
    job.run(worker.sessions, MORNING + timedelta(minutes=1))  # no accounts: quick no-op
    assert not job.nudged
