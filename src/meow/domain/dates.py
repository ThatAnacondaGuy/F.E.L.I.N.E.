"""Deterministic reading of deadline phrases ("this Friday, 5 PM", "3 Oct", "tomorrow noon").

Local models are unreliable at weekday arithmetic (qwen3 put "this Friday" on a Wednesday),
so the model copies the deadline wording and this module resolves it. If the phrase can't be
read, the model's own answer stands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time, timedelta

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
END_OF_DAY = time(23, 59)

_WEEKDAY_RE = re.compile(
    r"\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(?:day|nesday|rsday|urday|sday)?\b"
)
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DAY_MONTH_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}(?:,?\s+(\d{{4}}))?"
)
_MONTH_DAY_RE = re.compile(rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?")
# Indian day/month order. Without a year only "/" counts, so a time like "10.30" isn't a date.
_NUMERIC_RE = re.compile(
    r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b|\b(\d{1,2})[.-](\d{1,2})[.-](\d{2,4})\b"
)
_TIME_12_RE = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*([ap])\.?\s*m\b\.?")
_TIME_24_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


@dataclass(frozen=True, slots=True)
class Resolved:
    day: date
    clock: time | None  # None when the phrase names no time


def _month_index(token: str) -> int:
    return next(i for i, m in enumerate(MONTHS, 1) if m.startswith(token[:3]))


def _year_for(day: int, month: int, reference: date) -> int:
    """No year given: pick the one that makes the date nearest (deadlines are rarely months old)."""
    candidate = date(reference.year, month, day)
    if (reference - candidate).days > 60:
        return reference.year + 1
    return reference.year


def read_time(text: str) -> time | None:
    if re.search(r"\bnoon\b|\bmidday\b", text):
        return time(12, 0)
    if re.search(r"\bmidnight\b|\beod\b|\bend of (the )?day\b", text):
        return END_OF_DAY
    if m := _TIME_12_RE.search(text):
        hour, minute = int(m.group(1)) % 12, int(m.group(2) or 0)
        if m.group(3) == "p":
            hour += 12
        if minute < 60:
            return time(hour, minute)
    if m := _TIME_24_RE.search(text):
        return time(int(m.group(1)), int(m.group(2)))
    return None


def read_date(text: str, reference: date) -> date | None:
    if re.search(r"\bday after tomorrow\b", text):
        return reference + timedelta(days=2)
    if re.search(r"\byesterday\b", text):
        return reference - timedelta(days=1)
    if re.search(r"\btomorrow\b|\btmrw\b|\btmr\b", text):
        return reference + timedelta(days=1)
    if re.search(r"\btoday\b|\btonight\b", text):
        return reference
    for regex, day_group, month_group, year_group in (
        (_DAY_MONTH_RE, 1, 2, 3),
        (_MONTH_DAY_RE, 2, 1, 3),
    ):
        if m := regex.search(text):
            day, month = int(m.group(day_group)), _month_index(m.group(month_group))
            year = int(m.group(year_group)) if m.group(year_group) else None
            try:
                return date(year or _year_for(day, month, reference), month, day)
            except ValueError:
                return None
    if m := _NUMERIC_RE.search(text):
        groups = m.groups()[:3] if m.group(1) else m.groups()[3:]
        day, month = int(groups[0]), int(groups[1])
        year = int(groups[2]) if groups[2] else None
        if year is not None and year < 100:
            year += 2000
        try:
            return date(year or _year_for(day, month, reference), month, day)
        except ValueError:
            pass  # not a date after all; a weekday may still be there
    if m := _WEEKDAY_RE.search(text):
        target = next(i for i, w in enumerate(WEEKDAYS) if w.startswith(m.group(1)[:3]))
        if re.search(r"\b(last|previous|past)\s+$", text[: m.start()]):
            # "last Friday": the most recent one before today.
            return reference - timedelta(days=(reference.weekday() - target) % 7 or 7)
        # "Friday", "this Friday", "by Friday", "next Friday": the coming one. Naming today's
        # weekday means next week (people say "today" for today).
        ahead = (target - reference.weekday()) % 7 or 7
        return reference + timedelta(days=ahead)
    return None


_TIME_CUE_RE = re.compile(
    r"\b(today|tonight|tomorrow|tmrw|yesterday|week|weekend|month|days?|hours?|noon|midnight"
    r"|eod|deadline|due|until|till|kal|parso|aaj|baje|din|tak|raat|shaam|subah)\b"
    r"|\b\d{1,2}(st|nd|rd|th)\b"
)


def mentions_time(phrase: str) -> bool:
    """Does the wording talk about *when* at all? ("form groups of 3" does not.)"""
    text = phrase.lower()
    return bool(_TIME_CUE_RE.search(text) or read_time(text) or read_date(text, date(2000, 1, 3)))


def resolve(phrase: str, reference: date) -> Resolved | None:
    """Read a deadline phrase relative to ``reference`` (the day the message was sent)."""
    text = phrase.lower()
    day = read_date(text, reference)
    if day is None:
        return None
    return Resolved(day=day, clock=read_time(text))
