"""Extraction evals: run the real extractor over labelled messages and score it.

A case is one message plus the tasks a careful human would take from it. Predicted tasks are
matched to expected ones by an *anchor*: a distinctive phrase from the source that the
prediction's evidence quote (or title) must contain. Evidence is verbatim by construction, so
anchors are easy to write and robust to however the model phrases the title.

Scores:
- precision / recall / F1 over tasks
- deadline accuracy: matched tasks whose deadline is right (to the minute, or the day when
  the label only gives a date; "no deadline" must stay empty)
- course accuracy: matched tasks with the right course code (or rightly none)
- clean negatives: messages with nothing to do that produced nothing
- latency per message
"""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from meow.config import Profile
from meow.llm.extraction import (
    Candidate,
    ExtractionError,
    Extractor,
    SourceText,
    normalize_text,
)

SEED_PATH = Path(__file__).with_name("seed_extraction.jsonl")


ANY_COURSE = "*"


class ExpectedTask(BaseModel):
    anchor: list[str] = Field(min_length=1)  # any of these phrases identifies the task
    # "YYYY-MM-DDTHH:MM" (exact minute), "YYYY-MM-DD" (day only), a list of acceptable
    # values for genuinely ambiguous wording, or null for "no deadline".
    due: str | list[str] | None = None
    course: str | None = None  # a course code, null for none, or "*" for either
    optional: bool = False  # debatable items: credited if found, not penalised if missed


class Case(BaseModel):
    id: str
    sent: datetime
    kind: str = "gmail"
    title: str = ""
    author: str | None = None
    body: str
    expected: list[ExpectedTask] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    def source(self) -> SourceText:
        return SourceText(
            body=self.body,
            title=self.title,
            author=self.author,
            occurred_at=self.sent,
            kind=self.kind,
        )


def load_cases(path: Path) -> list[Case]:
    cases = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip() and not line.lstrip().startswith("#"):
            try:
                cases.append(Case.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"{path}:{number}: {exc}") from exc
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate case ids")
    return cases


def save_cases(cases: Iterable[Case], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(c.model_dump_json(exclude_defaults=True) + "\n" for c in cases))


# ── scoring one case ─────────────────────────────────────────────────────


@dataclass(slots=True)
class Match:
    anchor: str
    predicted_title: str | None
    due_ok: bool | None = None  # None when unmatched, or not checked (optional items)
    course_ok: bool | None = None
    expected_due: str | list[str] | None = None
    predicted_due: str | None = None
    optional: bool = False


@dataclass(slots=True)
class CaseResult:
    id: str
    tags: list[str]
    seconds: float
    expected: int
    predicted: int
    negative: bool  # the message asks nothing at all
    matches: list[Match] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)
    dropped: int = 0
    error: str | None = None

    @property
    def true_positives(self) -> int:
        return sum(1 for m in self.matches if m.predicted_title is not None)

    @property
    def missed(self) -> list[str]:
        return [m.anchor for m in self.matches if m.predicted_title is None]


def _hits(candidate: Candidate, anchors: Sequence[str]) -> bool:
    haystack = normalize_text(f"{candidate.draft.title} || {candidate.evidence}")
    return any(normalize_text(a) in haystack for a in anchors)


def due_matches(expected: str | list[str] | None, shown: str | None) -> bool:
    if expected is None:
        return shown is None
    if shown is None:
        return False
    options = [expected] if isinstance(expected, str) else expected
    return any(shown[:10] == o if len(o) == 10 else shown == o for o in options)


def score_case(
    case: Case,
    candidates: Sequence[Candidate],
    profile: Profile,
    *,
    seconds: float,
    dropped: int = 0,
) -> CaseResult:
    result = CaseResult(
        case.id,
        case.tags,
        round(seconds, 2),
        0,
        len(candidates),
        negative=not case.expected,
        dropped=dropped,
    )
    unused = list(candidates)
    # Required tasks pick first, so an optional one never steals their match.
    for exp in sorted(case.expected, key=lambda e: e.optional):
        found = next((c for c in unused if _hits(c, exp.anchor)), None)
        if found is None:
            if not exp.optional:
                result.expected += 1
                result.matches.append(Match(exp.anchor[0], None, expected_due=exp.due))
            continue
        unused.remove(found)
        result.expected += 1
        if exp.optional:
            result.matches.append(Match(exp.anchor[0], found.draft.title, optional=True))
            continue
        due = found.draft.due_at
        shown = due.astimezone(profile.user.tz).strftime("%Y-%m-%dT%H:%M") if due else None
        course_ok = exp.course == ANY_COURSE or found.draft.course_code == exp.course
        result.matches.append(
            Match(
                exp.anchor[0],
                found.draft.title,
                due_matches(exp.due, shown),
                course_ok,
                exp.due,
                shown,
            )
        )
    result.false_positives = [c.draft.title for c in unused]
    return result


# ── running and summarising ──────────────────────────────────────────────


@dataclass(slots=True)
class Summary:
    model: str
    think: bool | None
    cases: int
    precision: float
    recall: float
    f1: float
    deadline_accuracy: float
    course_accuracy: float
    clean_negatives: str  # "4/5"
    errors: int
    p50_seconds: float
    p95_seconds: float
    total_seconds: float


def summarise(results: Sequence[CaseResult], model: str, think: bool | None) -> Summary:
    tp = sum(r.true_positives for r in results)
    predicted = sum(r.predicted for r in results)
    expected = sum(r.expected for r in results)
    matched = [m for r in results for m in r.matches if m.predicted_title is not None]
    negatives = [r for r in results if r.negative]
    times = sorted(r.seconds for r in results) or [0.0]
    precision = tp / predicted if predicted else 1.0
    recall = tp / expected if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    def rate(flags: list[bool | None]) -> float:
        checked = [f for f in flags if f is not None]
        return sum(1 for f in checked if f) / len(checked) if checked else 1.0

    return Summary(
        model=model,
        think=think,
        cases=len(results),
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
        deadline_accuracy=round(rate([m.due_ok for m in matched]), 3),
        course_accuracy=round(rate([m.course_ok for m in matched]), 3),
        clean_negatives=f"{sum(1 for r in negatives if r.predicted == 0)}/{len(negatives)}",
        errors=sum(1 for r in results if r.error),
        p50_seconds=round(statistics.median(times), 2),
        p95_seconds=round(times[min(len(times) - 1, round(0.95 * (len(times) - 1)))], 2),
        total_seconds=round(sum(times), 1),
    )


def run_eval(
    cases: Sequence[Case], extractor: Extractor, profile: Profile, progress: Any = None
) -> list[CaseResult]:
    results = []
    for case in cases:
        start = time.perf_counter()
        try:
            report = extractor.extract(case.source(), case.sent)
        except ExtractionError as exc:
            elapsed = time.perf_counter() - start
            result = score_case(case, [], profile, seconds=elapsed)
            result.error = str(exc)[:300]
        else:
            elapsed = time.perf_counter() - start
            result = score_case(
                case, report.candidates, profile, seconds=elapsed, dropped=len(report.dropped)
            )
        results.append(result)
        if progress:
            progress(result)
    return results


def write_report(path: Path, summary: Summary, results: Sequence[CaseResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"summary": asdict(summary), "cases": [asdict(r) for r in results]}, indent=2)
    )
