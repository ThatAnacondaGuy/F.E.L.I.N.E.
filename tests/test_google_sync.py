from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from meow.config import Profile, Settings
from meow.db.models import AuditEntry, CalendarEvent, ConnectedAccount, Proposal, SourceItem
from meow.integrations.google.auth import ReauthRequired
from meow.integrations.google.sync import GoogleSync
from meow.services import accounts, capture, proposals, syncing, tasks
from meow.types import ProposalKind, ProposalStatus, SourceKind

from support import (
    FakeAPIs,
    FakeCalendar,
    FakeClassroom,
    FakeGmail,
    FakeLLM,
    MemoryTokenStore,
    extracted,
    fake_credentials,
    gmail_msg,
    ist,
)

ME = "me@gmail.test"
NOW = ist(2026, 9, 28, 18, 0)
ALL = [SourceKind.GMAIL, SourceKind.CALENDAR, SourceKind.CLASSROOM]


@pytest.fixture
def account(db: Session) -> ConnectedAccount:
    return accounts.connect(db, ME, ALL)


def sync(db: Session, profile: Profile, apis: FakeAPIs, now=NOW, load=fake_credentials, **kw: Any):  # type: ignore[no-untyped-def]
    return GoogleSync(db, profile, MemoryTokenStore(), apis, now, load).run(**kw)


# ── Gmail ────────────────────────────────────────────────────────────────


def emails() -> FakeGmail:
    return FakeGmail(
        [
            gmail_msg(
                "m1", "CN Lab 4", "Submit lab assignment 4 by Friday 11:59 PM.", ist(2026, 9, 27, 9)
            ),
            gmail_msg(
                "m2", "Seminar", "Send your synopsis draft by Wednesday.", ist(2026, 9, 26, 9)
            ),
            gmail_msg("m3", "Newsletter", "This week in campus news.", ist(2026, 9, 25, 9)),
        ]
    )


def test_first_gmail_sync_reads_the_lookback_window(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    gmail = emails()
    report = sync(db, profile, FakeAPIs(gmail=gmail), source=SourceKind.GMAIL)
    (result,) = report.results
    assert result.new_items == 3 and result.error is None
    after = int((NOW - timedelta(days=profile.sync.gmail_lookback_days)).timestamp())
    assert gmail.queries[0] == f"{profile.sync.gmail_query} after:{after}"
    assert db.query(SourceItem).filter_by(kind=SourceKind.GMAIL).count() == 3


def test_resync_skips_known_messages_and_moves_the_cursor(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    gmail = emails()
    sync(db, profile, FakeAPIs(gmail=gmail), source=SourceKind.GMAIL)
    fetched = len(gmail.fetched)
    report = sync(db, profile, FakeAPIs(gmail=gmail), source=SourceKind.GMAIL)
    assert report.results[0].new_items == 0
    assert len(gmail.fetched) == fetched  # nothing downloaded twice
    newest = int(ist(2026, 9, 27, 9).timestamp())
    assert gmail.queries[-1].endswith(f"after:{newest - 3600}")


# ── Classroom ────────────────────────────────────────────────────────────


def classroom(**overrides: Any) -> FakeClassroom:
    work = {
        "id": "w1",
        "title": "Assignment 2: A* search",
        "state": "PUBLISHED",
        "description": "Implement A* on a grid.",
        "alternateLink": "https://classroom.test/w1",
        "creationTime": "2026-09-25T04:00:00Z",
        "updateTime": "2026-09-25T04:00:00Z",
        "dueDate": {"year": 2026, "month": 9, "day": 30},
        "dueTime": {"hours": 18, "minutes": 29},
    }
    work.update(overrides)
    return FakeClassroom(
        courses=[{"id": "c1", "name": "TE AI 2026-27"}],
        coursework={
            "c1": [
                work,
                {
                    "id": "w2",
                    "title": "Lab 1",
                    "state": "PUBLISHED",
                    "updateTime": "2026-09-20T04:00:00Z",
                },
                {
                    "id": "w3",
                    "title": "Draft quiz",
                    "state": "DRAFT",
                    "updateTime": "2026-09-26T04:00:00Z",
                },
            ]
        },
        announcements={
            "c1": [
                {
                    "id": "a1",
                    "text": "Unit test on Friday, bring calculators.",
                    "state": "PUBLISHED",
                    "creationTime": "2026-09-27T04:00:00Z",
                }
            ]
        },
        states={"c1": {"w2": "TURNED_IN"}},
    )


def test_coursework_becomes_proposals_without_the_model(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    report = sync(db, profile, FakeAPIs(classroom=classroom()), source=SourceKind.CLASSROOM)
    (result,) = report.results
    assert result.error is None and result.proposals == 1  # w2 turned in, w3 is a draft
    (p,) = proposals.list_proposals(db)
    assert p.created_by == "classroom" and p.confidence == 1.0
    assert p.payload["title"] == "Assignment 2: A* search"
    assert p.payload["course_code"] == "PCC301COM"  # matched by the "AI" alias
    assert p.payload["career_relevance"] == 0.6
    assert tasks.TaskDraft.model_validate(p.payload).due_at == ist(2026, 9, 30, 23, 59)
    assert p.evidence == "Assignment 2: A* search"


def test_announcements_wait_for_the_model(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    sync(db, profile, FakeAPIs(classroom=classroom()), source=SourceKind.CLASSROOM)
    pending = capture.pending_extraction(db, 50)
    assert [i.external_id for i in pending] == ["announcement:a1"]
    assert pending[0].body.startswith("Course: Artificial Intelligence")


def test_resync_is_idempotent(db: Session, profile: Profile, account: ConnectedAccount) -> None:
    apis = FakeAPIs(classroom=classroom())
    sync(db, profile, apis, source=SourceKind.CLASSROOM)
    report = sync(db, profile, apis, source=SourceKind.CLASSROOM)
    assert report.results[0].proposals == 0 and report.results[0].new_items == 0
    assert db.query(Proposal).count() == 1


def test_changed_deadline_replaces_the_pending_proposal(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    sync(db, profile, FakeAPIs(classroom=classroom()), source=SourceKind.CLASSROOM)
    moved = classroom(
        dueDate={"year": 2026, "month": 10, "day": 3}, updateTime="2026-09-28T04:00:00Z"
    )
    sync(db, profile, FakeAPIs(classroom=moved), source=SourceKind.CLASSROOM)
    statuses = sorted(p.status.value for p in db.query(Proposal))
    assert statuses == ["pending", "superseded"]
    (live,) = proposals.list_proposals(db)
    assert tasks.TaskDraft.model_validate(live.payload).due_at == ist(2026, 10, 3, 23, 59)


def test_approved_work_is_not_proposed_again_when_it_changes(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    sync(db, profile, FakeAPIs(classroom=classroom()), source=SourceKind.CLASSROOM)
    proposals.approve(db, profile, proposals.list_proposals(db)[0].id)
    sync(
        db,
        profile,
        FakeAPIs(classroom=classroom(description="Now with diagrams.")),
        source=SourceKind.CLASSROOM,
    )
    assert proposals.list_proposals(db) == []
    assert db.query(AuditEntry).filter_by(action="source.changed").count() == 1


def test_long_overdue_work_is_not_proposed(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    old = classroom(dueDate={"year": 2026, "month": 9, "day": 1})
    sync(db, profile, FakeAPIs(classroom=old), source=SourceKind.CLASSROOM)
    assert proposals.list_proposals(db) == []


# ── Calendar ─────────────────────────────────────────────────────────────


def calendar(*event_ids: str) -> FakeCalendar:
    events = {
        "e1": {
            "id": "e1",
            "summary": "CSI meeting",
            "start": {"dateTime": "2026-09-28T13:00:00Z"},
            "end": {"dateTime": "2026-09-28T14:00:00Z"},
        },
        "e2": {
            "id": "e2",
            "summary": "Gym (free)",
            "transparency": "transparent",
            "start": {"dateTime": "2026-09-28T15:00:00Z"},
            "end": {"dateTime": "2026-09-28T16:00:00Z"},
        },
        "e3": {
            "id": "e3",
            "summary": "Navratri",
            "start": {"date": "2026-09-29"},
            "end": {"date": "2026-09-30"},
        },
    }
    return FakeCalendar([events[i] for i in event_ids])


def test_calendar_events_become_busy_time(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    sync(db, profile, FakeAPIs(calendar=calendar("e1", "e2", "e3")), source=SourceKind.CALENDAR)
    busy = {e.external_id: e.busy for e in db.query(CalendarEvent)}
    assert busy == {"e1": True, "e2": False, "e3": False}
    tasks.add_task(db, tasks.TaskDraft(title="Essay", estimated_minutes=60))
    plan = tasks.build_plan(db, profile, NOW)
    # The 18:30-19:30 IST meeting (+15 min buffers) pushes the first session to 19:45.
    assert plan.sessions[0].interval.start == ist(2026, 9, 28, 19, 45)


def test_events_deleted_upstream_disappear(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    sync(db, profile, FakeAPIs(calendar=calendar("e1", "e2")), source=SourceKind.CALENDAR)
    sync(db, profile, FakeAPIs(calendar=calendar("e2")), source=SourceKind.CALENDAR)
    assert [e.external_id for e in db.query(CalendarEvent)] == ["e2"]


# ── failure handling ─────────────────────────────────────────────────────


def test_expired_sign_in_flags_the_account(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    def expired(store: object, email: str, sources: object) -> object:
        raise ReauthRequired(f"Google ended the session for {email}")

    report = sync(db, profile, FakeAPIs(), load=expired)
    assert report.reauth_needed == [ME]
    db.refresh(account)
    assert account.needs_reauth and "ended the session" in (account.last_error or "")

    sync(db, profile, FakeAPIs())  # signing in again clears it
    db.refresh(account)
    assert not account.needs_reauth


def test_one_source_failing_does_not_stop_the_others(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    class BrokenGmail(FakeGmail):
        def list_message_ids(self, query: str, page_token: str | None) -> Any:
            raise RuntimeError("Gmail API has not been used in project 123")

    report = sync(db, profile, FakeAPIs(gmail=BrokenGmail([]), calendar=calendar("e1")))
    errors = {r.source: r.error for r in report.results}
    assert "has not been used" in (errors[SourceKind.GMAIL] or "")
    assert errors[SourceKind.CALENDAR] is None
    assert db.query(CalendarEvent).count() == 1
    states = {st.source: st for st in accounts.sync_states(db, ME)}
    assert states[SourceKind.GMAIL].last_error and states[SourceKind.CALENDAR].last_success_at


def test_disconnected_accounts_are_skipped(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    accounts.disconnect(db, ME)
    assert sync(db, profile, FakeAPIs(gmail=emails())).results == []


# ── the full run: sync, then let the model read ──────────────────────────


def test_run_sync_reads_new_email_with_the_model(
    db: Session, settings: Settings, account: ConnectedAccount
) -> None:
    llm = FakeLLM(
        lambda user: {
            "tasks": [extracted(evidence="Submit lab assignment 4 by Friday 11:59 PM")]
            if "lab assignment 4" in user
            else []
        }
    )
    run = syncing.run_sync(
        db,
        settings,
        NOW,
        llm=llm,
        apis=FakeAPIs(gmail=emails(), classroom=classroom()),
        store=MemoryTokenStore(),
        load=fake_credentials,
    )
    # 3 emails + 1 announcement go to the model; coursework never does.
    assert len(llm.calls) == 4
    assert run.extraction.processed == 4 and run.extraction.proposals == 1
    kinds = sorted(p.created_by for p in db.query(Proposal))
    assert kinds == ["classroom", "extractor"]
    assert capture.pending_extraction(db, 50) == []


def test_extraction_stops_politely_when_ollama_is_down(
    db: Session, settings: Settings, account: ConnectedAccount
) -> None:
    from meow.llm.ollama import LLMError

    def down(_: str) -> object:
        raise LLMError("Ollama unreachable (connection refused). Is `ollama serve` running?")

    llm = FakeLLM(down)
    run = syncing.run_sync(
        db,
        settings,
        NOW,
        llm=llm,
        apis=FakeAPIs(gmail=emails()),
        store=MemoryTokenStore(),
        load=fake_credentials,
    )
    assert len(llm.calls) == 1  # stopped after the first failure
    assert run.extraction.error and "unreachable" in run.extraction.error
    assert run.google.new_items == 3  # the sync itself still happened
    assert len(capture.pending_extraction(db, 50)) == 3  # they wait for next time


def test_only_one_sync_at_a_time(db: Session, settings: Settings) -> None:
    assert syncing._lock.acquire(blocking=False)
    try:
        with pytest.raises(syncing.SyncBusy):
            syncing.run_sync(
                db,
                settings,
                NOW,
                llm=None,
                apis=FakeAPIs(),
                store=MemoryTokenStore(),
                load=fake_credentials,
            )
    finally:
        syncing._lock.release()


def test_proposals_from_sync_respect_autonomy(
    db: Session, profile: Profile, account: ConnectedAccount
) -> None:
    sync(db, profile, FakeAPIs(classroom=classroom()), source=SourceKind.CLASSROOM)
    (p,) = proposals.list_proposals(db)
    assert p.status is ProposalStatus.PENDING and p.kind is ProposalKind.CREATE_TASK
