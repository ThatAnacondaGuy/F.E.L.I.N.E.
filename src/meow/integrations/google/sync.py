"""Pull Gmail, Calendar and Classroom into Meow.

- Gmail messages and Classroom announcements become source items for the model to read.
- Classroom coursework is structured (title, due date, course), so it becomes task proposals
  directly, with no model in the loop. Work you've already turned in is skipped.
- Calendar events become busy time for the planner.

Each (account, source) pair syncs independently: one failing never stops the others.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from meow.config import Profile
from meow.db.models import (
    CalendarEvent,
    ConnectedAccount,
    FocusSession,
    Proposal,
    SourceItem,
    SyncState,
    Task,
)
from meow.integrations.google import normalize
from meow.integrations.google.apis import (
    CalendarAPI,
    ClassroomAPI,
    GmailAPI,
    GoogleCalendar,
    GoogleClassroom,
    GoogleGmail,
    is_permission_error,
)
from meow.integrations.google.auth import ReauthRequired, TokenStore, load_credentials
from meow.services import accounts, audit, proposals
from meow.services.capture import Change, upsert_source
from meow.services.tasks import TaskDraft
from meow.types import Category, Importance, ProposalKind, ProposalStatus, SourceKind, TaskStatus

log = logging.getLogger(__name__)

DONE_STATES = {"TURNED_IN", "RETURNED"}
STALE_AFTER = timedelta(days=7)  # overdue coursework older than this isn't proposed


class APIs(Protocol):
    def gmail(self, credentials: Any) -> GmailAPI: ...
    def calendar(self, credentials: Any) -> CalendarAPI: ...
    def classroom(self, credentials: Any) -> ClassroomAPI: ...


class GoogleAPIs:
    def gmail(self, credentials: Any) -> GmailAPI:
        return GoogleGmail(credentials)

    def calendar(self, credentials: Any) -> CalendarAPI:
        return GoogleCalendar(credentials)

    def classroom(self, credentials: Any) -> ClassroomAPI:
        return GoogleClassroom(credentials)


CredentialLoader = Callable[[TokenStore, str, Iterable[SourceKind]], Any]


@dataclass(slots=True)
class SourceResult:
    account: str
    source: SourceKind
    new_items: int = 0
    proposals: int = 0
    pushed: int = 0  # focus blocks added to the Meow calendar
    removed: int = 0  # focus blocks taken off it (task done, block gone)
    error: str | None = None


@dataclass(slots=True)
class SyncReport:
    results: list[SourceResult] = field(default_factory=list)
    reauth_needed: list[str] = field(default_factory=list)

    @property
    def new_items(self) -> int:
        return sum(r.new_items for r in self.results)

    @property
    def proposals(self) -> int:
        return sum(r.proposals for r in self.results)

    @property
    def errors(self) -> list[SourceResult]:
        return [r for r in self.results if r.error]


def _short(exc: Exception) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return text[:300]


class GoogleSync:
    def __init__(
        self,
        db: Session,
        profile: Profile,
        store: TokenStore,
        apis: APIs,
        now: datetime,
        load: CredentialLoader = load_credentials,
    ) -> None:
        self.db, self.profile, self.store, self.apis, self.now = db, profile, store, apis, now
        self.load = load
        self.tz = profile.user.tz

    # ── orchestration ────────────────────────────────────────────────────

    def run(self, *, account: str | None = None, source: SourceKind | None = None) -> SyncReport:
        report = SyncReport()
        enabled = accounts.list_accounts(self.db, enabled_only=True)
        self.focus_account = self._focus_account(enabled)
        for acct in enabled:
            if account and acct.email != accounts.normalize_email(account):
                continue
            wanted = [SourceKind(s) for s in acct.sources if source is None or s == source]
            if wanted:
                self._run_account(acct, wanted, report)
        return report

    def _run_account(
        self, acct: ConnectedAccount, sources: Sequence[SourceKind], report: SyncReport
    ) -> None:
        try:
            creds = self.load(self.store, acct.email, sources)
        except ReauthRequired as exc:
            accounts.mark_needs_reauth(self.db, acct, _short(exc))
            self.db.commit()
            report.reauth_needed.append(acct.email)
            report.results += [SourceResult(acct.email, s, error=_short(exc)) for s in sources]
            return
        acct.needs_reauth, acct.last_error = False, None
        for src in sources:
            result = SourceResult(acct.email, src)
            state = self._state(src, acct.email)
            state.last_attempt_at = self.now
            try:
                if src is SourceKind.GMAIL:
                    self._sync_gmail(self.apis.gmail(creds), acct.email, state, result)
                elif src is SourceKind.CALENDAR:
                    calendar = self.apis.calendar(creds)
                    self._sync_calendar(calendar, acct.email, result)
                    if acct.email == self.focus_account:
                        self.db.commit()  # keep the busy time even if the push fails
                        try:
                            self._push_focus_blocks(calendar, acct, result)
                        except Exception as exc:
                            self.db.rollback()
                            result.error = f"focus calendar: {_short(exc)}"
                            log.warning("focus push for %s failed: %s", acct.email, exc)
                elif src is SourceKind.CLASSROOM:
                    self._sync_classroom(self.apis.classroom(creds), acct.email, result)
            except Exception as exc:  # isolate: one source failing never blocks the rest
                self.db.rollback()
                state = self._state(src, acct.email)
                state.last_attempt_at = self.now
                result.error = _short(exc)
                if is_permission_error(exc):
                    result.error = f"Google refused access ({result.error})"
                log.warning("sync %s/%s failed: %s", acct.email, src.value, result.error)
            state.last_error = result.error
            if result.error is None:
                state.last_success_at = self.now
                state.items_new = result.new_items
            if result.error:
                acct.last_error = f"{src.value}: {result.error}"
            audit.record(
                self.db,
                actor="sync",
                action="sync.source",
                entity_type="account",
                account=acct.email,
                source=src.value,
                new=result.new_items,
                proposals=result.proposals,
                pushed=result.pushed,
                removed=result.removed,
                error=result.error,
            )
            self.db.commit()
            report.results.append(result)

    def _focus_account(self, enabled: Sequence[ConnectedAccount]) -> str | None:
        """The one account whose calendar gets the focus blocks."""
        cfg = self.profile.sync
        if not cfg.push_focus_blocks:
            return None
        if cfg.focus_calendar_account:
            return accounts.normalize_email(cfg.focus_calendar_account)
        return next((a.email for a in enabled if SourceKind.CALENDAR.value in a.sources), None)

    def _state(self, source: SourceKind, account: str) -> SyncState:
        state = self.db.scalar(
            select(SyncState).where(SyncState.source == source, SyncState.account == account)
        )
        if state is None:
            state = SyncState(source=source, account=account)
            self.db.add(state)
        return state

    # ── Gmail ────────────────────────────────────────────────────────────

    def _sync_gmail(
        self, api: GmailAPI, account: str, state: SyncState, result: SourceResult
    ) -> None:
        cfg = self.profile.sync
        if state.cursor:
            after = int(state.cursor) - 3600  # an hour of overlap; duplicates are skipped
        else:
            after = int((self.now - timedelta(days=cfg.gmail_lookback_days)).timestamp())
        query = f"{cfg.gmail_query} after:{after}".strip()
        ids: list[str] = []
        token: str | None = None
        while len(ids) < cfg.gmail_max_messages:
            page, token = api.list_message_ids(query, token)
            ids += page
            if not token:
                break
        ids = ids[: cfg.gmail_max_messages]
        known = set(
            self.db.scalars(
                select(SourceItem.external_id).where(
                    SourceItem.kind == SourceKind.GMAIL,
                    SourceItem.account == account,
                    SourceItem.external_id.in_(ids),
                )
            )
        )
        newest = int(state.cursor) if state.cursor else after
        for message_id in ids:
            if message_id in known:
                continue
            draft = normalize.gmail_message(api.get_message(message_id), account)
            _, change = upsert_source(
                self.db,
                kind=SourceKind.GMAIL,
                account=account,
                external_id=draft.external_id,
                title=draft.title,
                body=draft.body,
                author=draft.author,
                url=draft.url,
                occurred_at=draft.occurred_at,
            )
            if change is Change.NEW:
                result.new_items += 1
            if draft.occurred_at:
                newest = max(newest, int(draft.occurred_at.timestamp()))
        state.cursor = str(newest)

    # ── Calendar ─────────────────────────────────────────────────────────

    def _sync_calendar(self, api: CalendarAPI, account: str, result: SourceResult) -> None:
        start = self.now - timedelta(days=1)
        end = self.now + timedelta(days=self.profile.planner.horizon_days + 2)
        for calendar_id in self.profile.sync.calendar_ids:
            seen: set[str] = set()
            token: str | None = None
            while True:
                items, token = api.list_events(calendar_id, start, end, token)
                for raw in items:
                    event = normalize.calendar_event(raw, self.tz)
                    if event is None:
                        continue
                    seen.add(event.external_id)
                    result.new_items += self._upsert_event(account, calendar_id, event)
                if not token:
                    break
            # Events deleted or cancelled upstream disappear here too.
            self.db.execute(
                delete(CalendarEvent).where(
                    CalendarEvent.account == account,
                    CalendarEvent.calendar_id == calendar_id,
                    CalendarEvent.start_at >= start,
                    CalendarEvent.start_at < end,
                    CalendarEvent.external_id.not_in(seen),
                )
            )

    def _upsert_event(self, account: str, calendar_id: str, event: normalize.BusyEvent) -> int:
        row = self.db.scalar(
            select(CalendarEvent).where(
                CalendarEvent.account == account,
                CalendarEvent.calendar_id == calendar_id,
                CalendarEvent.external_id == event.external_id,
            )
        )
        created = row is None
        if row is None:
            row = CalendarEvent(
                account=account, calendar_id=calendar_id, external_id=event.external_id
            )
            self.db.add(row)
        row.title, row.start_at, row.end_at = event.title, event.start_at, event.end_at
        row.all_day, row.busy = event.all_day, event.busy
        return int(created)

    # ── Focus blocks → the "Meow focus" calendar ─────────────────────────

    def _push_focus_blocks(
        self, api: CalendarAPI, acct: ConnectedAccount, result: SourceResult
    ) -> None:
        """Make the Meow calendar match your approved focus blocks: add missing ones, remove
        ones whose block or task is gone. Events Meow didn't create are never touched."""
        cfg = self.profile.sync
        calendar_id = acct.focus_calendar_id
        if not calendar_id or not api.calendar_exists(calendar_id):
            calendar_id = api.create_calendar(
                cfg.focus_calendar_name,
                "Focus blocks you approved in Meow OS. Meow only ever edits this calendar.",
                self.profile.user.timezone,
            )
            acct.focus_calendar_id = calendar_id
            audit.record(
                self.db,
                actor="sync",
                action="calendar.created",
                entity_type="account",
                account=acct.email,
                name=cfg.focus_calendar_name,
            )
            self.db.flush()
        start = self.now - timedelta(days=1)
        end = self.now + timedelta(days=self.profile.planner.horizon_days + 2)

        remote: dict[str, str] = {}  # focus session id -> event id
        token: str | None = None
        while True:
            items, token = api.list_events(calendar_id, start, end, token)
            for event in items:
                private = (event.get("extendedProperties") or {}).get("private") or {}
                if session_id := private.get("meow_session_id"):
                    remote[session_id] = event["id"]
            if not token:
                break

        sessions = self.db.scalars(
            select(FocusSession)
            .join(Task)
            .where(
                FocusSession.end_at > start,
                FocusSession.start_at < end,
                Task.status == TaskStatus.TODO,
            )
        )
        wanted: set[str] = set()
        for session in sessions:
            wanted.add(session.id)
            if session.id in remote:
                session.calendar_event_id = remote[session.id]
                continue
            session.calendar_event_id = api.insert_event(calendar_id, self._event_body(session))
            result.pushed += 1
        for session_id, event_id in remote.items():
            if session_id not in wanted:
                api.delete_event(calendar_id, event_id)
                result.removed += 1

    def _event_body(self, session: FocusSession) -> dict[str, Any]:
        tz_name = self.profile.user.timezone
        minutes = self.profile.sync.focus_reminder_minutes
        return {
            "summary": f"Focus: {session.task.title}",
            "description": "Planned by Meow OS from a focus block you approved.",
            "start": {
                "dateTime": session.start_at.astimezone(self.tz).isoformat(),
                "timeZone": tz_name,
            },
            "end": {
                "dateTime": session.end_at.astimezone(self.tz).isoformat(),
                "timeZone": tz_name,
            },
            "transparency": "opaque",
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": minutes}] if minutes else [],
            },
            "extendedProperties": {
                "private": {"meow_session_id": session.id, "meow_task_id": session.task_id}
            },
        }

    # ── Classroom ────────────────────────────────────────────────────────

    def _sync_classroom(self, api: ClassroomAPI, account: str, result: SourceResult) -> None:
        cutoff = self.now - timedelta(days=self.profile.sync.classroom_lookback_days)
        for course in api.list_courses():
            mapped = normalize.match_course(course, self.profile.courses)
            label = mapped.name if mapped else str(course.get("name", "Classroom"))
            try:
                states = api.my_submission_states(course["id"])
            except Exception as exc:  # submissions are a nicety; don't fail the course
                log.info("submission states unavailable for %s: %s", course.get("id"), exc)
                states = {}
            for work in api.list_coursework(course["id"]):
                updated = normalize.parse_rfc3339(
                    work.get("updateTime") or work.get("creationTime")
                )
                if work.get("state", "PUBLISHED") != "PUBLISHED" or (updated and updated < cutoff):
                    continue
                self._coursework(
                    work, course, mapped, label, states.get(work["id"], ""), account, result
                )
            for ann in api.list_announcements(course["id"]):
                created = normalize.parse_rfc3339(ann.get("creationTime"))
                if ann.get("state", "PUBLISHED") != "PUBLISHED" or (created and created < cutoff):
                    continue
                text = normalize.tidy_text(ann.get("text", ""))
                if not text:
                    continue
                _, change = upsert_source(
                    self.db,
                    kind=SourceKind.CLASSROOM,
                    account=account,
                    external_id=f"announcement:{ann['id']}",
                    title=f"{label}: announcement",
                    body=f"Course: {label}\n\n{text}",
                    url=ann.get("alternateLink"),
                    occurred_at=created,
                )
                result.new_items += change is Change.NEW

    def _coursework(
        self,
        work: dict[str, Any],
        course: dict[str, Any],
        mapped: Any,
        label: str,
        submission_state: str,
        account: str,
        result: SourceResult,
    ) -> None:
        due = normalize.coursework_due(work, self.tz)
        item, change = upsert_source(
            self.db,
            kind=SourceKind.CLASSROOM,
            account=account,
            external_id=f"coursework:{work['id']}",
            title=str(work.get("title", "Classroom assignment"))[:500],
            body=normalize.coursework_text(work, label, due, self.tz),
            url=work.get("alternateLink"),
            occurred_at=normalize.parse_rfc3339(work.get("creationTime")),
        )
        if change is Change.NEW:
            result.new_items += 1
        if change is Change.SAME:
            return
        pending = list(
            self.db.scalars(
                select(Proposal).where(
                    Proposal.source_item_id == item.id, Proposal.status == ProposalStatus.PENDING
                )
            )
        )
        for old in pending:  # the assignment changed before you decided: replace the proposal
            old.status, old.decided_at, old.decided_by = (
                ProposalStatus.SUPERSEDED,
                self.now,
                "sync",
            )
        already_approved = self.db.scalar(
            select(Proposal.id).where(
                Proposal.source_item_id == item.id,
                Proposal.status.in_([ProposalStatus.APPROVED, ProposalStatus.AUTO_APPROVED]),
            )
        )
        item.extracted_at = self.now  # structured source: nothing for the model to read
        done = submission_state in DONE_STATES
        stale = due is not None and due < self.now - STALE_AFTER
        if done or stale or already_approved:
            return
        draft = TaskDraft(
            title=str(work.get("title", "Classroom assignment")).strip()[:200] or "Assignment",
            notes=f"From Google Classroom: {label}",
            importance=Importance.MEDIUM,
            category=Category.ACADEMIC,
            due_at=due,
            course_code=mapped.code if mapped else None,
            career_relevance=mapped.career_relevance if mapped else 0.0,
        )
        proposals.propose(
            self.db,
            self.profile,
            ProposalKind.CREATE_TASK,
            draft.model_dump(mode="json"),
            created_by="classroom",
            evidence=draft.title,
            confidence=1.0,
            source_item_id=item.id,
        )
        result.proposals += 1
