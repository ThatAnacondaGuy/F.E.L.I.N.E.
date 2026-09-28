from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from meow.config import Profile
from meow.db.models import FocusSession
from meow.integrations.google.sync import GoogleSync, SyncReport
from meow.services import accounts, planning, proposals, tasks
from meow.types import ProposalKind, SourceKind, TaskStatus

from support import FakeAPIs, FakeCalendar, MemoryTokenStore, fake_credentials, ist

ME = "me@gmail.test"
NOW = ist(2026, 9, 28, 16, 0)


@pytest.fixture
def cal() -> FakeCalendar:
    return FakeCalendar([])


def sync(db: Session, profile: Profile, cal: FakeCalendar) -> SyncReport:
    return GoogleSync(
        db, profile, MemoryTokenStore(), FakeAPIs(calendar=cal), NOW, fake_credentials
    ).run()


def plan_and_approve(db: Session, profile: Profile, minutes: int = 90) -> str:
    task = tasks.add_task(db, tasks.TaskDraft(title="AI assignment 2", estimated_minutes=minutes))
    planning.propose_focus_blocks(db, profile, NOW)
    proposals.approve_all(db, profile, ProposalKind.SCHEDULE_FOCUS_BLOCK)
    return task.id


def meow_events(cal: FakeCalendar) -> list[dict[str, Any]]:
    (calendar,) = cal.owned.values()
    return list(calendar.values())


def test_approved_blocks_land_on_a_calendar_meow_creates(
    db: Session, profile: Profile, cal: FakeCalendar
) -> None:
    accounts.connect(db, ME, [SourceKind.CALENDAR])
    plan_and_approve(db, profile)
    report = sync(db, profile, cal)
    assert report.results[0].pushed == 1 and report.results[0].error is None
    assert list(cal.names.values()) == ["Meow focus"]
    (event,) = meow_events(cal)
    assert event["summary"] == "Focus: AI assignment 2"
    assert event["start"] == {"dateTime": "2026-09-28T16:30:00+05:30", "timeZone": "Asia/Kolkata"}
    assert event["end"]["dateTime"] == "2026-09-28T18:00:00+05:30"
    assert event["reminders"]["overrides"] == [{"method": "popup", "minutes": 5}]
    session = db.query(FocusSession).one()
    assert event["extendedProperties"]["private"]["meow_session_id"] == session.id
    assert session.calendar_event_id is not None


def test_resync_creates_nothing_twice(db: Session, profile: Profile, cal: FakeCalendar) -> None:
    accounts.connect(db, ME, [SourceKind.CALENDAR])
    plan_and_approve(db, profile)
    sync(db, profile, cal)
    report = sync(db, profile, cal)
    assert (report.results[0].pushed, report.results[0].removed) == (0, 0)
    assert len(cal.owned) == 1 and len(meow_events(cal)) == 1


def test_unapproved_blocks_stay_off_the_calendar(
    db: Session, profile: Profile, cal: FakeCalendar
) -> None:
    accounts.connect(db, ME, [SourceKind.CALENDAR])
    tasks.add_task(db, tasks.TaskDraft(title="Essay", estimated_minutes=60))
    planning.propose_focus_blocks(db, profile, NOW)  # proposed, not approved
    sync(db, profile, cal)
    assert meow_events(cal) == []


def test_finishing_a_task_clears_its_blocks_from_the_calendar(
    db: Session, profile: Profile, cal: FakeCalendar
) -> None:
    accounts.connect(db, ME, [SourceKind.CALENDAR])
    task_id = plan_and_approve(db, profile)
    sync(db, profile, cal)
    tasks.set_status(db, task_id, TaskStatus.DONE, actor="user", now=NOW)
    assert db.query(FocusSession).count() == 0
    report = sync(db, profile, cal)
    assert report.results[0].removed == 1 and meow_events(cal) == []


def test_a_deleted_meow_calendar_is_recreated(
    db: Session, profile: Profile, cal: FakeCalendar
) -> None:
    accounts.connect(db, ME, [SourceKind.CALENDAR])
    plan_and_approve(db, profile)
    sync(db, profile, cal)
    cal.owned.clear()  # you deleted it in Google Calendar
    report = sync(db, profile, cal)
    assert report.results[0].pushed == 1 and len(meow_events(cal)) == 1


def test_events_meow_did_not_create_are_never_touched(
    db: Session, profile: Profile, cal: FakeCalendar
) -> None:
    accounts.connect(db, ME, [SourceKind.CALENDAR])
    sync(db, profile, cal)
    (calendar_id,) = cal.owned
    cal.owned[calendar_id]["mine"] = {"summary": "Something you added yourself"}
    sync(db, profile, cal)
    assert "mine" in cal.owned[calendar_id]


def test_only_one_account_gets_the_focus_calendar(
    db: Session, profile: Profile, cal: FakeCalendar
) -> None:
    accounts.connect(db, ME, [SourceKind.CALENDAR])
    accounts.connect(db, "college@college.test", [SourceKind.CALENDAR])
    plan_and_approve(db, profile)
    report = sync(db, profile, cal)
    pushed = {r.account: r.pushed for r in report.results}
    assert pushed == {ME: 1, "college@college.test": 0}
    assert len(cal.owned) == 1


def test_pushing_can_be_turned_off(db: Session, profile: Profile, cal: FakeCalendar) -> None:
    off = profile.model_copy(
        update={"sync": profile.sync.model_copy(update={"push_focus_blocks": False})}
    )
    accounts.connect(db, ME, [SourceKind.CALENDAR])
    plan_and_approve(db, off)
    sync(db, off, cal)
    assert cal.owned == {}


def test_a_failed_push_keeps_the_busy_time(db: Session, profile: Profile) -> None:
    class ReadOnlyCalendar(FakeCalendar):
        def create_calendar(self, summary: str, description: str, time_zone: str) -> str:
            raise RuntimeError("Request had insufficient authentication scopes.")

    busy = {
        "id": "e1",
        "summary": "CSI meeting",
        "start": {"dateTime": "2026-09-28T13:00:00Z"},
        "end": {"dateTime": "2026-09-28T14:00:00Z"},
    }
    accounts.connect(db, ME, [SourceKind.CALENDAR])
    report = sync(db, profile, ReadOnlyCalendar([busy]))
    (result,) = report.results
    assert result.error is not None and result.error.startswith("focus calendar:")
    assert result.new_items == 1
    from meow.db.models import CalendarEvent

    assert db.query(CalendarEvent).count() == 1  # the pull was not rolled back
