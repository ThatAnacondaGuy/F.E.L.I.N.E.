"""Turn unstructured text into task candidates, and verify them before anyone sees them.

The model proposes; this module checks. A candidate survives only if its evidence quote
really appears in the source. Dates are interpreted in your timezone and sanity-checked.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from string import Template

from pydantic import BaseModel, Field, ValidationError

from meow.config import Profile
from meow.domain import dates
from meow.llm.ollama import JSONChat, LLMError
from meow.services.tasks import TaskDraft
from meow.types import BlockKind, Category, Importance

PROMPT = Template((Path(__file__).parent / "prompts" / "extract_tasks.md").read_text())
MAX_SOURCE_CHARS = 12_000


class ExtractedTask(BaseModel):
    """The shape the model must return (sent to Ollama as a JSON schema)."""

    title: str
    evidence: str
    due_phrase: str | None  # the deadline words exactly as written; code resolves them
    due: str | None
    estimated_minutes: int | None
    importance: Importance
    category: Category
    course_code: str | None
    career_relevance: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)


class ExtractionOutput(BaseModel):
    tasks: list[ExtractedTask]


@dataclass(frozen=True, slots=True)
class SourceText:
    body: str
    title: str = ""
    author: str | None = None
    occurred_at: datetime | None = None
    kind: str = "manual"


@dataclass(frozen=True, slots=True)
class Candidate:
    draft: TaskDraft
    evidence: str
    confidence: float
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class ExtractionReport:
    candidates: list[Candidate] = field(default_factory=list)
    dropped: list[tuple[str, str]] = field(default_factory=list)  # (title, reason)


class ExtractionError(RuntimeError):
    pass


_TYPOGRAPHY = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-"})


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_TYPOGRAPHY)
    return re.sub(r"\s+", " ", text).strip().casefold()


def evidence_in_source(evidence: str, source: str) -> bool:
    """Every fragment of the quote (split on ellipses) must appear in the source."""
    haystack = _normalize(source)
    fragments = [f.strip(" \"'") for f in re.split(r"\.\.\.|…", _normalize(evidence))]
    fragments = [f for f in fragments if f]
    return bool(fragments) and all(f in haystack for f in fragments)


class Extractor:
    def __init__(self, llm: JSONChat, profile: Profile) -> None:
        self.llm = llm
        self.profile = profile

    def system_prompt(self, now: datetime, sent: datetime | None = None) -> str:
        user = self.profile.user
        courses = "\n".join(
            f"- {c.code}: {c.name} ({c.priority.value} priority)" for c in self.profile.courses
        )
        start = (sent or now).astimezone(user.tz).date()
        calendar = "\n".join(
            f"- {start + timedelta(days=i):%A %d %B %Y}"
            + (" (the day it was sent)" if i == 0 else "")
            for i in range(15)
        )
        return PROMPT.substitute(
            name=user.name,
            career_goal=user.career_goal,
            now=now.astimezone(user.tz).strftime("%A %Y-%m-%d %H:%M"),
            timezone=user.timezone,
            courses=courses,
            calendar=calendar,
            college_start=self._college_start(),
        )

    def _college_start(self) -> str:
        starts = [b.start for b in self.profile.schedule if b.kind is BlockKind.COLLEGE]
        return min(starts).strftime("%H:%M") if starts else "09:00"

    def user_message(self, source: SourceText) -> str:
        header = [f"Source type: {source.kind}"]
        if source.title:
            header.append(f"Subject/title: {source.title}")
        if source.author:
            header.append(f"From: {source.author}")
        if source.occurred_at:
            sent = source.occurred_at.astimezone(self.profile.user.tz)
            header.append(f"Sent: {sent:%A %Y-%m-%d %H:%M}")
        body = source.body[:MAX_SOURCE_CHARS]
        return "\n".join(header) + "\n\n---\n" + body

    def extract(self, source: SourceText, now: datetime) -> ExtractionReport:
        try:
            raw = self.llm.chat_json(
                self.profile.llm.extract_model,
                self.system_prompt(now, source.occurred_at),
                self.user_message(source),
                ExtractionOutput.model_json_schema(),
            )
        except LLMError as exc:
            raise ExtractionError(str(exc)) from exc
        try:
            output = ExtractionOutput.model_validate(raw)
        except ValidationError as exc:
            raise ExtractionError(f"model output did not match the schema: {exc}") from exc

        report = ExtractionReport()
        searchable = f"{source.title}\n{source.body}"
        for item in output.tasks:
            if not evidence_in_source(item.evidence, searchable):
                report.dropped.append((item.title, "evidence quote not found in the source"))
                continue
            candidate = self._to_candidate(item, source, now)
            if isinstance(candidate, str):
                report.dropped.append((item.title, candidate))
            else:
                report.candidates.append(candidate)
        return report

    def _to_candidate(
        self, item: ExtractedTask, source: SourceText, now: datetime
    ) -> Candidate | str:
        notes: list[str] = []
        confidence = item.confidence
        due = self._parse_due(item.due)
        if item.due and due is None:
            notes.append(f"couldn't read deadline {item.due!r}")
            confidence *= 0.5
        reference = source.occurred_at or now
        due = self._check_phrase(item.due_phrase, due, source, reference, notes)
        if due is not None and due < reference - timedelta(days=1):
            notes.append("deadline was before the message was sent; ignored it")
            due, confidence = None, confidence * 0.5
        course = item.course_code if self.profile.course(item.course_code) else None
        if item.course_code and course is None:
            notes.append(f"unknown course {item.course_code!r}")
        career = item.career_relevance
        if matched := self.profile.course(course):
            # Coursework's career value is a setting you own, not a model's guess.
            career = matched.career_relevance
        minutes = item.estimated_minutes
        if minutes is not None and not 0 < minutes <= 24 * 60 * 14:
            minutes = None
        try:
            draft = TaskDraft(
                title=item.title[:200],
                importance=item.importance,
                category=item.category,
                due_at=due,
                estimated_minutes=minutes,
                course_code=course,
                career_relevance=career,
            )
        except ValidationError as exc:
            return f"invalid task fields: {exc.errors()[0]['msg']}"
        return Candidate(draft, item.evidence.strip(), round(confidence, 3), tuple(notes))

    def _check_phrase(
        self,
        phrase: str | None,
        due: datetime | None,
        source: SourceText,
        reference: datetime,
        notes: list[str],
    ) -> datetime | None:
        """Resolve the quoted deadline wording in code and prefer it over the model's date."""
        if not phrase or not evidence_in_source(phrase, f"{source.title}\n{source.body}"):
            return due
        tz = self.profile.user.tz
        resolved = dates.resolve(phrase, reference.astimezone(tz).date())
        if resolved is None:
            return due
        clock = resolved.clock or (
            due.astimezone(tz).timetz().replace(tzinfo=None) if due else dates.END_OF_DAY
        )
        fixed = datetime.combine(resolved.day, clock, tzinfo=tz)
        if due is not None and fixed != due:
            notes.append(
                f"deadline corrected from {due.astimezone(tz):%a %d %b %H:%M} to match "
                f"\u201c{phrase.strip()}\u201d"
            )
        return fixed

    def _parse_due(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=self.profile.user.tz)
        return parsed
