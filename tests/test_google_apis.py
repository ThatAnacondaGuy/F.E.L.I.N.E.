"""Drive the real googleapiclient code against a recording transport: this checks the exact
endpoints, parameters and bodies Meow sends, without a network or a Google account."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httplib2
import pytest

from meow.integrations.google.apis import GoogleCalendar, GoogleClassroom, GoogleGmail

from support import ist


class RecordingHttp:
    """Answers each request with the next canned (status, json) and records what was sent."""

    def __init__(self, *responses: tuple[int, dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def request(
        self, uri: str, method: str = "GET", body: Any = None, headers: Any = None, **kwargs: Any
    ) -> tuple[httplib2.Response, bytes]:
        parts = urlsplit(uri)
        self.requests.append(
            {
                "method": method,
                "path": unquote(parts.path),
                "query": {
                    k: v if len(v) > 1 else v[0]
                    for k, v in parse_qs(parts.query).items()
                    if k != "alt"  # the client always asks for JSON
                },
                "body": json.loads(body) if body else None,
            }
        )
        status, payload = self.responses.pop(0)
        return httplib2.Response({"status": status}), json.dumps(payload).encode()


def test_gmail_list_and_get() -> None:
    http = RecordingHttp(
        (200, {"messages": [{"id": "a"}], "nextPageToken": "p2"}), (200, {"id": "a", "payload": {}})
    )
    gmail = GoogleGmail(None, http=http)
    assert gmail.list_message_ids("in:inbox after:1", None) == (["a"], "p2")
    gmail.get_message("a")
    listing, get = http.requests
    assert listing["path"] == "/gmail/v1/users/me/messages"
    assert listing["query"]["q"] == "in:inbox after:1" and listing["query"]["maxResults"] == "100"
    assert get["path"] == "/gmail/v1/users/me/messages/a" and get["query"]["format"] == "full"


def test_calendar_reads_expanded_events_in_a_window() -> None:
    http = RecordingHttp((200, {"items": [{"id": "e1"}]}))
    items, token = GoogleCalendar(None, http=http).list_events(
        "primary", ist(2026, 9, 28), ist(2026, 10, 7), None
    )
    assert items == [{"id": "e1"}] and token is None
    (req,) = http.requests
    assert req["path"] == "/calendar/v3/calendars/primary/events"
    assert req["query"]["singleEvents"] == "true" and req["query"]["orderBy"] == "startTime"
    assert req["query"]["timeMin"] == "2026-09-28T00:00:00+05:30"


def test_calendar_creates_its_own_calendar_and_events() -> None:
    http = RecordingHttp(
        (200, {"id": "meowcal@group.calendar.google.com"}), (200, {"id": "ev1"}), (204, {})
    )
    cal = GoogleCalendar(None, http=http)
    cal_id = cal.create_calendar("Meow focus", "desc", "Asia/Kolkata")
    event_id = cal.insert_event(cal_id, {"summary": "Focus: X"})
    cal.delete_event(cal_id, event_id)
    create, insert, delete = http.requests
    assert (create["method"], create["path"]) == ("POST", "/calendar/v3/calendars")
    assert create["body"] == {
        "summary": "Meow focus",
        "description": "desc",
        "timeZone": "Asia/Kolkata",
    }
    assert insert["path"] == "/calendar/v3/calendars/meowcal@group.calendar.google.com/events"
    assert insert["body"] == {"summary": "Focus: X"} and event_id == "ev1"
    assert delete["method"] == "DELETE" and delete["path"].endswith("/events/ev1")


def test_calendar_treats_gone_as_gone() -> None:
    http = RecordingHttp((404, {"error": {"code": 404}}), (410, {"error": {"code": 410}}))
    cal = GoogleCalendar(None, http=http)
    assert cal.calendar_exists("deleted") is False
    cal.delete_event("c", "already-deleted")  # no exception


def test_calendar_permission_errors_are_raised() -> None:
    from googleapiclient.errors import HttpError

    from meow.integrations.google.apis import is_permission_error

    cal = GoogleCalendar(None, http=RecordingHttp((403, {"error": {"code": 403}})))
    with pytest.raises(HttpError) as info:
        cal.calendar_exists("someone-elses")
    assert is_permission_error(info.value)


def test_classroom_student_endpoints_and_paging() -> None:
    http = RecordingHttp(
        (200, {"courses": [{"id": "c1"}], "nextPageToken": "n"}),
        (200, {"courses": [{"id": "c2"}]}),
        (200, {"studentSubmissions": [{"courseWorkId": "w1", "state": "TURNED_IN"}]}),
    )
    room = GoogleClassroom(None, http=http)
    assert [c["id"] for c in room.list_courses()] == ["c1", "c2"]
    assert room.my_submission_states("c1") == {"w1": "TURNED_IN"}
    first, second, subs = http.requests
    assert first["query"] == {"studentId": "me", "courseStates": "ACTIVE", "pageSize": "100"}
    assert second["query"]["pageToken"] == "n"
    assert subs["path"] == "/v1/courses/c1/courseWork/-/studentSubmissions"
    assert subs["query"]["userId"] == "me"
