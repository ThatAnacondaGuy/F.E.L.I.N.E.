"""Helpers shared by the tests (importable as `support` via pytest's pythonpath)."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def ist(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=IST)


class FakeLLM:
    """Returns canned JSON and records what it was asked."""

    def __init__(self, response: Any | Callable[[str], Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def chat_json(self, model: str, system: str, user: str, schema: dict[str, Any]) -> Any:
        self.calls.append({"model": model, "system": system, "user": user, "schema": schema})
        if callable(self.response):
            return self.response(user)
        return json.loads(json.dumps(self.response))


def extracted(**overrides: Any) -> dict[str, Any]:
    """One task as the model would return it."""
    item = {
        "title": "Submit CN lab assignment 4",
        "evidence": "Submit lab assignment 4 by Friday 11:59 PM",
        "due_phrase": "by Friday 11:59 PM",
        "due": "2026-10-02T23:59",
        "estimated_minutes": 90,
        "importance": "high",
        "category": "academic",
        "course_code": "PCC302COM",
        "career_relevance": 0.1,
        "confidence": 0.9,
    }
    item.update(overrides)
    return item


LAB_EMAIL = (
    "Dear students,\n\nSubmit lab assignment 4 by Friday 11:59 PM on the portal. "
    "Late submissions will not be accepted.\n\nRegards,\nProf. Kulkarni"
)


# ── Google fakes ─────────────────────────────────────────────────────────


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def gmail_msg(
    message_id: str,
    subject: str,
    body: str,
    sent: datetime,
    sender: str = "Prof. Kulkarni <kulkarni@college.test>",
) -> dict[str, Any]:
    return {
        "id": message_id,
        "internalDate": str(int(sent.timestamp() * 1000)),
        "snippet": body[:40],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [{"name": "Subject", "value": subject}, {"name": "From", "value": sender}],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": b64(body)}},
                {"mimeType": "text/html", "body": {"data": b64(f"<p>{body}</p>")}},
            ],
        },
    }


class FakeGmail:
    def __init__(self, messages: list[dict[str, Any]], page_size: int = 2) -> None:
        self.messages = {m["id"]: m for m in messages}
        self.page_size = page_size
        self.queries: list[str] = []
        self.fetched: list[str] = []

    def list_message_ids(self, query: str, page_token: str | None) -> tuple[list[str], str | None]:
        self.queries.append(query)
        ids = list(self.messages)
        start = int(page_token or 0)
        end = start + self.page_size
        return ids[start:end], (str(end) if end < len(ids) else None)

    def get_message(self, message_id: str) -> dict[str, Any]:
        self.fetched.append(message_id)
        return self.messages[message_id]


class FakeCalendar:
    """Your primary calendar (read) plus any calendars Meow creates (read/write), in memory."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events
        self.owned: dict[str, dict[str, dict[str, Any]]] = {}  # calendar id -> event id -> body
        self.names: dict[str, str] = {}
        self._next = 0

    def _id(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}{self._next}"

    def list_events(
        self, calendar_id: str, time_min: datetime, time_max: datetime, page_token: str | None
    ) -> tuple[list[dict[str, Any]], str | None]:
        if calendar_id in self.owned:
            return [{"id": eid, **body} for eid, body in self.owned[calendar_id].items()], None
        return list(self.events), None

    def calendar_exists(self, calendar_id: str) -> bool:
        return calendar_id in self.owned

    def create_calendar(self, summary: str, description: str, time_zone: str) -> str:
        calendar_id = self._id("meowcal")
        self.owned[calendar_id], self.names[calendar_id] = {}, summary
        return calendar_id

    def insert_event(self, calendar_id: str, body: dict[str, Any]) -> str:
        event_id = self._id("ev")
        self.owned[calendar_id][event_id] = body
        return event_id

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        self.owned[calendar_id].pop(event_id, None)


class FakeClassroom:
    def __init__(
        self,
        courses: list[dict[str, Any]],
        coursework: dict[str, list[dict[str, Any]]],
        announcements: dict[str, list[dict[str, Any]]] | None = None,
        states: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.courses, self.coursework = courses, coursework
        self.announcements = announcements or {}
        self.states = states or {}

    def list_courses(self) -> list[dict[str, Any]]:
        return self.courses

    def list_coursework(self, course_id: str) -> list[dict[str, Any]]:
        return self.coursework.get(course_id, [])

    def list_announcements(self, course_id: str) -> list[dict[str, Any]]:
        return self.announcements.get(course_id, [])

    def my_submission_states(self, course_id: str) -> dict[str, str]:
        return self.states.get(course_id, {})


class FakeAPIs:
    def __init__(self, gmail: Any = None, calendar: Any = None, classroom: Any = None) -> None:
        self._gmail = gmail or FakeGmail([])
        self._calendar = calendar or FakeCalendar([])
        self._classroom = classroom or FakeClassroom([], {})

    def gmail(self, credentials: Any) -> Any:
        return self._gmail

    def calendar(self, credentials: Any) -> Any:
        return self._calendar

    def classroom(self, credentials: Any) -> Any:
        return self._classroom


class MemoryTokenStore:
    def __init__(self, tokens: dict[str, str] | None = None) -> None:
        self.tokens = dict(tokens or {})

    def load(self, email: str) -> str | None:
        return self.tokens.get(email)

    def save(self, email: str, token_json: str) -> None:
        self.tokens[email] = token_json

    def delete(self, email: str) -> None:
        self.tokens.pop(email, None)


def fake_credentials(store: Any, email: str, sources: Any) -> object:
    return object()


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> bool:
        self.sent.append((title, message))
        return True
