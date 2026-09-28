"""The only code that talks to Google. Everything above it depends on these small protocols,
so sync logic is tested with in-memory fakes instead of network mocks."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any, Protocol

Page = tuple[list[dict[str, Any]], str | None]


class GmailAPI(Protocol):
    def list_message_ids(
        self, query: str, page_token: str | None
    ) -> tuple[list[str], str | None]: ...

    def get_message(self, message_id: str) -> dict[str, Any]: ...


class CalendarAPI(Protocol):
    def list_events(
        self, calendar_id: str, time_min: datetime, time_max: datetime, page_token: str | None
    ) -> Page: ...

    # Writing is limited to the calendar Meow creates (scope: calendar.app.created).
    def calendar_exists(self, calendar_id: str) -> bool: ...
    def create_calendar(self, summary: str, description: str, time_zone: str) -> str: ...
    def insert_event(self, calendar_id: str, body: dict[str, Any]) -> str: ...
    def delete_event(self, calendar_id: str, event_id: str) -> None: ...


class ClassroomAPI(Protocol):
    def list_courses(self) -> list[dict[str, Any]]: ...
    def list_coursework(self, course_id: str) -> list[dict[str, Any]]: ...
    def list_announcements(self, course_id: str) -> list[dict[str, Any]]: ...
    def my_submission_states(self, course_id: str) -> dict[str, str]: ...


def _pages(fetch: Callable[[str | None], dict[str, Any]], key: str) -> Iterator[dict[str, Any]]:
    token: str | None = None
    while True:
        response = fetch(token)
        yield from response.get(key, [])
        token = response.get("nextPageToken")
        if not token:
            return


def _build(api: str, version: str, credentials: Any, http: Any = None) -> Any:
    """``http`` lets tests drive the real client against a recorded transport."""
    from googleapiclient.discovery import build

    if http is not None:
        return build(api, version, http=http, cache_discovery=False, static_discovery=True)
    return build(
        api, version, credentials=credentials, cache_discovery=False, static_discovery=True
    )


class GoogleGmail:
    def __init__(self, credentials: Any, http: Any = None) -> None:
        self._svc = _build("gmail", "v1", credentials, http)

    def list_message_ids(self, query: str, page_token: str | None) -> tuple[list[str], str | None]:
        resp = (
            self._svc.users()
            .messages()
            .list(userId="me", q=query, maxResults=100, pageToken=page_token)
            .execute()
        )
        return [m["id"] for m in resp.get("messages", [])], resp.get("nextPageToken")

    def get_message(self, message_id: str) -> dict[str, Any]:
        msg: dict[str, Any] = (
            self._svc.users().messages().get(userId="me", id=message_id, format="full").execute()
        )
        return msg


class GoogleCalendar:
    def __init__(self, credentials: Any, http: Any = None) -> None:
        self._svc = _build("calendar", "v3", credentials, http)

    def list_events(
        self, calendar_id: str, time_min: datetime, time_max: datetime, page_token: str | None
    ) -> Page:
        resp = (
            self._svc.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=250,
                pageToken=page_token,
            )
            .execute()
        )
        return resp.get("items", []), resp.get("nextPageToken")

    def calendar_exists(self, calendar_id: str) -> bool:
        try:
            self._svc.calendars().get(calendarId=calendar_id).execute()
        except Exception as exc:
            if _status(exc) in (404, 410):
                return False
            raise
        return True

    def create_calendar(self, summary: str, description: str, time_zone: str) -> str:
        body = {"summary": summary, "description": description, "timeZone": time_zone}
        return str(self._svc.calendars().insert(body=body).execute()["id"])

    def insert_event(self, calendar_id: str, body: dict[str, Any]) -> str:
        return str(self._svc.events().insert(calendarId=calendar_id, body=body).execute()["id"])

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        try:
            self._svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        except Exception as exc:
            if _status(exc) not in (404, 410):  # already gone is fine
                raise


class GoogleClassroom:
    def __init__(self, credentials: Any, http: Any = None) -> None:
        self._svc = _build("classroom", "v1", credentials, http)

    def list_courses(self) -> list[dict[str, Any]]:
        courses = self._svc.courses()
        return list(
            _pages(
                lambda t: courses.list(
                    studentId="me", courseStates=["ACTIVE"], pageSize=100, pageToken=t
                ).execute(),
                "courses",
            )
        )

    def list_coursework(self, course_id: str) -> list[dict[str, Any]]:
        work = self._svc.courses().courseWork()
        return list(
            _pages(
                lambda t: work.list(
                    courseId=course_id, orderBy="updateTime desc", pageSize=100, pageToken=t
                ).execute(),
                "courseWork",
            )
        )

    def list_announcements(self, course_id: str) -> list[dict[str, Any]]:
        ann = self._svc.courses().announcements()
        return list(
            _pages(
                lambda t: ann.list(
                    courseId=course_id, orderBy="updateTime desc", pageSize=50, pageToken=t
                ).execute(),
                "announcements",
            )
        )

    def my_submission_states(self, course_id: str) -> dict[str, str]:
        subs = self._svc.courses().courseWork().studentSubmissions()
        items = _pages(
            lambda t: subs.list(
                courseId=course_id, courseWorkId="-", userId="me", pageSize=100, pageToken=t
            ).execute(),
            "studentSubmissions",
        )
        return {s["courseWorkId"]: s.get("state", "") for s in items}


def _status(exc: Exception) -> int | None:
    from googleapiclient.errors import HttpError

    return int(exc.resp.status) if isinstance(exc, HttpError) else None


def is_permission_error(exc: Exception) -> bool:
    """True for 401/403 responses (revoked access, or an admin blocking the app)."""
    return _status(exc) in (401, 403)
