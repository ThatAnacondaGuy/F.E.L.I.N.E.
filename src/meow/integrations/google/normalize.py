"""Pure functions that turn Google API payloads into Meow's shapes. No network, fully tested."""

from __future__ import annotations

import base64
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

from meow.config import Course

MAX_BODY_CHARS = 12_000

# ── Gmail ────────────────────────────────────────────────────────────────


class _TextExtractor(HTMLParser):
    BLOCK: ClassVar = frozenset(
        {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol"}
    )
    SKIP: ClassVar = frozenset({"script", "style", "head", "title"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skipping += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skipping:
            self._skipping -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return tidy_text("".join(parser.parts))


def tidy_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _collect(part: dict[str, Any], found: dict[str, list[str]]) -> None:
    mime = part.get("mimeType", "")
    if part.get("filename"):  # attachments
        return
    data = part.get("body", {}).get("data")
    if data and mime in ("text/plain", "text/html"):
        found[mime].append(_decode(data))
    for child in part.get("parts", []) or []:
        _collect(child, found)


def message_body(payload: dict[str, Any]) -> str:
    """Prefer the plain-text part; fall back to HTML stripped to text."""
    found: dict[str, list[str]] = {"text/plain": [], "text/html": []}
    _collect(payload, found)
    if found["text/plain"]:
        return tidy_text("\n\n".join(found["text/plain"]))
    if found["text/html"]:
        return html_to_text("\n".join(found["text/html"]))
    return ""


@dataclass(frozen=True, slots=True)
class SourceDraft:
    """Everything needed to store a source item."""

    external_id: str
    title: str
    body: str
    author: str | None
    url: str | None
    occurred_at: datetime | None


def gmail_message(message: dict[str, Any], account: str) -> SourceDraft:
    payload = message.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    occurred: datetime | None = None
    if "internalDate" in message:
        occurred = datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=UTC)
    elif "date" in headers:
        try:
            occurred = parsedate_to_datetime(headers["date"]).astimezone(UTC)
        except (TypeError, ValueError):
            occurred = None
    name, address = parseaddr(headers.get("from", ""))
    author = f"{name} <{address}>" if name and address else (address or name or None)
    body = message_body(payload) or message.get("snippet", "")
    return SourceDraft(
        external_id=message["id"],
        title=headers.get("subject", "(no subject)")[:500],
        body=body[:MAX_BODY_CHARS],
        author=author,
        url=f"https://mail.google.com/mail/u/{account}/#all/{message['id']}",
        occurred_at=occurred,
    )


# ── Classroom ────────────────────────────────────────────────────────────


def parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def coursework_due(work: dict[str, Any], tz: ZoneInfo) -> datetime | None:
    """Classroom gives the due date and time in UTC. A date without a time means end of day
    in your timezone (that's what the Classroom UI shows)."""
    due_date = work.get("dueDate")
    if not due_date or not all(k in due_date for k in ("year", "month", "day")):
        return None
    day = date(due_date["year"], due_date["month"], due_date["day"])
    due_time = work.get("dueTime")
    if due_time is None:
        return datetime.combine(day, time(23, 59), tzinfo=tz)
    clock = time(due_time.get("hours", 0), due_time.get("minutes", 0))
    return datetime.combine(day, clock, tzinfo=UTC)


def _words(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "


def match_course(classroom_course: dict[str, Any], courses: Sequence[Course]) -> Course | None:
    """Map a Classroom course to one of yours by code, full name, or alias (whole words only,
    so "AI" never matches inside "maintenance")."""
    haystack = _words(
        " ".join(
            str(classroom_course.get(k, ""))
            for k in ("name", "section", "descriptionHeading", "description")
        )
    )
    best: tuple[int, Course] | None = None
    for course in courses:
        for strength, needle in [(3, course.code), (2, course.name)] + [
            (1, alias) for alias in course.aliases
        ]:
            if needle and _words(needle) in haystack and (best is None or strength > best[0]):
                best = (strength, course)
    return best[1] if best else None


def coursework_text(
    work: dict[str, Any], course_name: str, due: datetime | None, tz: ZoneInfo
) -> str:
    lines = [work.get("title", "").strip(), ""]
    if description := (work.get("description") or "").strip():
        lines += [description, ""]
    lines.append(f"Course: {course_name}")
    if due:
        lines.append(f"Due: {due.astimezone(tz):%A %d %B %Y, %H:%M}")
    if points := work.get("maxPoints"):
        lines.append(f"Points: {points:g}")
    if titles := material_titles(work.get("materials")):
        lines.append("Materials: " + ", ".join(titles))
    return tidy_text("\n".join(lines))[:MAX_BODY_CHARS]


def material_titles(materials: list[dict[str, Any]] | None) -> list[str]:
    """Titles of attached materials. Drive files nest one level deeper than links or videos."""
    titles = []
    for material in materials or []:
        for value in material.values():
            inner = value.get("driveFile", value) if isinstance(value, dict) else None
            if isinstance(inner, dict) and inner.get("title"):
                titles.append(str(inner["title"]))
    return titles


# ── Calendar ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BusyEvent:
    external_id: str
    title: str
    start_at: datetime
    end_at: datetime
    all_day: bool
    busy: bool


def calendar_event(event: dict[str, Any], tz: ZoneInfo) -> BusyEvent | None:
    """Only real blocks of time count as busy: not all-day markers, not events marked
    'free', and not invitations you declined."""
    if event.get("status") == "cancelled":
        return None
    start, end = event.get("start", {}), event.get("end", {})
    all_day = "date" in start
    if all_day:
        start_at = datetime.combine(date.fromisoformat(start["date"]), time(0), tzinfo=tz)
        end_at = datetime.combine(date.fromisoformat(end["date"]), time(0), tzinfo=tz)
    else:
        begin, finish = parse_rfc3339(start.get("dateTime")), parse_rfc3339(end.get("dateTime"))
        if begin is None or finish is None:
            return None
        start_at, end_at = begin, finish
    if end_at <= start_at:
        return None
    declined = any(
        a.get("self") and a.get("responseStatus") == "declined"
        for a in event.get("attendees", []) or []
    )
    busy = not all_day and event.get("transparency") != "transparent" and not declined
    return BusyEvent(
        event["id"], (event.get("summary") or "(busy)")[:500], start_at, end_at, all_day, busy
    )
