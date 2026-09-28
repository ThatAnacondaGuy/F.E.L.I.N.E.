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


def _build(api: str, version: str, credentials: Any) -> Any:
    from googleapiclient.discovery import build

    return build(
        api, version, credentials=credentials, cache_discovery=False, static_discovery=True
    )


class GoogleGmail:
    def __init__(self, credentials: Any) -> None:
        self._svc = _build("gmail", "v1", credentials)

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
    def __init__(self, credentials: Any) -> None:
        self._svc = _build("calendar", "v3", credentials)

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


class GoogleClassroom:
    def __init__(self, credentials: Any) -> None:
        self._svc = _build("classroom", "v1", credentials)

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


def is_permission_error(exc: Exception) -> bool:
    """True for 401/403 responses (revoked access, or an admin blocking the app)."""
    from googleapiclient.errors import HttpError

    return isinstance(exc, HttpError) and exc.resp.status in (401, 403)
