from __future__ import annotations

import pytest

from meow.config import Profile
from meow.integrations.google import normalize as n

from support import IST, b64, gmail_msg, ist, utc


def test_plain_text_part_is_preferred() -> None:
    msg = gmail_msg("m1", "Lab", "Submit lab 4 by Friday.", ist(2026, 9, 28, 9, 0))
    assert n.message_body(msg["payload"]) == "Submit lab 4 by Friday."


def test_html_only_is_converted_to_readable_text() -> None:
    payload = {
        "mimeType": "text/html",
        "body": {
            "data": b64(
                "<html><head><style>p{color:red}</style></head><body>"
                "<p>Dear students,</p><p>Quiz on <b>Monday</b>&nbsp;at 10.</p>"
                "<script>track()</script></body></html>"
            )
        },
    }
    assert n.message_body(payload) == "Dear students,\n\nQuiz on Monday at 10."


def test_attachments_and_nested_parts() -> None:
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": b64("See attached rubric.")}},
                ],
            },
            {
                "mimeType": "text/plain",
                "filename": "rubric.txt",
                "body": {"data": b64("SHOULD NOT APPEAR")},
            },
        ],
    }
    assert n.message_body(payload) == "See attached rubric."


def test_gmail_message_fields() -> None:
    sent = ist(2026, 9, 28, 9, 30)
    draft = n.gmail_message(gmail_msg("abc", "CN Lab 4", "Submit it.", sent), "me@gmail.com")
    assert draft.external_id == "abc"
    assert draft.title == "CN Lab 4"
    assert draft.author == "Prof. Kulkarni <kulkarni@college.test>"
    assert draft.occurred_at == sent
    assert draft.url == "https://mail.google.com/mail/u/me@gmail.com/#all/abc"


def test_coursework_due_uses_utc_date_and_time() -> None:
    work = {
        "dueDate": {"year": 2026, "month": 10, "day": 2},
        "dueTime": {"hours": 18, "minutes": 29},
    }
    assert n.coursework_due(work, IST) == ist(2026, 10, 2, 23, 59)


def test_coursework_due_without_time_means_end_of_day_locally() -> None:
    assert n.coursework_due({"dueDate": {"year": 2026, "month": 10, "day": 2}}, IST) == ist(
        2026, 10, 2, 23, 59
    )
    assert n.coursework_due({}, IST) is None


@pytest.mark.parametrize(
    ("classroom", "expected"),
    [
        ({"name": "TE Comp", "section": "PCC301COM 2026-27"}, "PCC301COM"),  # code
        ({"name": "Theory of Computation (TE A)"}, "PCC303COM"),  # full name
        ({"name": "TE CN Div A"}, "PCC302COM"),  # alias, whole word
        ({"name": "Hostel maintenance notices"}, None),  # 'ai' inside a word never matches
        ({"name": "AI", "section": "MDM331COM"}, "MDM331COM"),  # code beats alias
    ],
)
def test_match_course(profile: Profile, classroom: dict[str, str], expected: str | None) -> None:
    course = n.match_course(classroom, profile.courses)
    assert (course.code if course else None) == expected


def test_coursework_text_lists_due_and_materials() -> None:
    work = {
        "title": "Assignment 2: A* search",
        "description": "Implement A*   on a grid.\n\n\n\nShow your heuristic.",
        "maxPoints": 10,
        "materials": [
            {"driveFile": {"driveFile": {"title": "grid_maps.pdf"}}},
            {"link": {"url": "https://example.test", "title": "Reference"}},
        ],
    }
    text = n.coursework_text(work, "Artificial Intelligence", ist(2026, 9, 30, 23, 59), IST)
    assert text.startswith("Assignment 2: A* search\n\nImplement A* on a grid.\n\nShow your")
    assert "Due: Wednesday 30 September 2026, 23:59" in text
    assert "Materials: grid_maps.pdf, Reference" in text


@pytest.mark.parametrize(
    ("event", "busy"),
    [
        (
            {
                "id": "1",
                "start": {"dateTime": "2026-09-28T12:00:00Z"},
                "end": {"dateTime": "2026-09-28T13:00:00Z"},
            },
            True,
        ),
        (
            {
                "id": "2",
                "transparency": "transparent",
                "start": {"dateTime": "2026-09-28T12:00:00Z"},
                "end": {"dateTime": "2026-09-28T13:00:00Z"},
            },
            False,
        ),
        (
            {
                "id": "3",
                "attendees": [{"self": True, "responseStatus": "declined"}],
                "start": {"dateTime": "2026-09-28T12:00:00Z"},
                "end": {"dateTime": "2026-09-28T13:00:00Z"},
            },
            False,
        ),
        ({"id": "4", "start": {"date": "2026-09-28"}, "end": {"date": "2026-09-29"}}, False),
    ],
)
def test_calendar_busy_rules(event: dict[str, object], busy: bool) -> None:
    parsed = n.calendar_event(event, IST)
    assert parsed is not None and parsed.busy is busy


def test_calendar_times_and_cancellations() -> None:
    timed = n.calendar_event(
        {
            "id": "1",
            "summary": "CSI meet",
            "start": {"dateTime": "2026-09-28T12:00:00Z"},
            "end": {"dateTime": "2026-09-28T13:00:00+00:00"},
        },
        IST,
    )
    assert (
        timed is not None and timed.start_at == utc(2026, 9, 28, 12) and timed.title == "CSI meet"
    )
    all_day = n.calendar_event(
        {"id": "2", "start": {"date": "2026-09-28"}, "end": {"date": "2026-09-29"}}, IST
    )
    assert all_day is not None and all_day.start_at == ist(2026, 9, 28)
    assert n.calendar_event({"id": "3", "status": "cancelled"}, IST) is None
