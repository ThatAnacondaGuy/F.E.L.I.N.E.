from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from meow.config import Profile
from meow.domain.prioritizer import Prioritizer, TaskFacts
from meow.types import Importance

from support import ist

NOW = ist(2026, 9, 28, 18, 0)
BASE = TaskFacts(
    title="Task",
    importance=Importance.MEDIUM,
    due_at=None,
    estimated_minutes=60,
    course_code=None,
    career_relevance=0.0,
)


@pytest.fixture
def scorer(profile: Profile) -> Prioritizer:
    return Prioritizer(profile.scoring, profile.courses)


def total(scorer: Prioritizer, **changes: object) -> float:
    return scorer.score(replace(BASE, **changes), NOW).total


def test_closer_deadlines_score_higher(scorer: Prioritizer) -> None:
    overdue = total(scorer, due_at=NOW - timedelta(hours=2))
    tomorrow = total(scorer, due_at=NOW + timedelta(days=1))
    next_week = total(scorer, due_at=NOW + timedelta(days=7))
    none = total(scorer, due_at=None)
    assert overdue > tomorrow > next_week > none


def test_no_slack_means_full_urgency(scorer: Prioritizer) -> None:
    # 3h of work due in 2h: already too late to finish comfortably.
    score = scorer.score(replace(BASE, due_at=NOW + timedelta(hours=2), estimated_minutes=180), NOW)
    urgency = next(f for f in score.factors if f.name == "urgency")
    assert urgency.value == 1.0
    assert "no slack" in urgency.reason


def test_urgency_halves_every_half_life_of_slack(scorer: Prioritizer, profile: Profile) -> None:
    half_life = profile.scoring.urgency_half_life_hours
    due = NOW + timedelta(hours=half_life + 1)  # 1h of work, so slack == half life
    urgency = next(
        f for f in scorer.score(replace(BASE, due_at=due), NOW).factors if f.name == "urgency"
    )
    assert urgency.value == pytest.approx(0.5)


def test_course_priority_comes_from_config(scorer: Prioritizer) -> None:
    ai = total(scorer, course_code="PCC301COM")
    networks = total(scorer, course_code="PCC302COM")
    unknown = total(scorer, course_code="NOPE101")
    assert ai > networks > unknown == total(scorer)


def test_career_relevance_is_a_field_not_a_keyword_guess(scorer: Prioritizer) -> None:
    # The old prototype scored this as NVIDIA-relevant because "ai" is inside "email"
    # and "maintenance", and "ml" is inside "html".
    email = replace(BASE, title="Reply to email about hostel maintenance html form")
    score = scorer.score(email, NOW)
    career = next(f for f in score.factors if f.name == "career")
    assert career.value == 0.0
    assert total(scorer, career_relevance=0.9) > score.total


def test_weights_sum_to_a_0_to_100_scale(scorer: Prioritizer) -> None:
    best = replace(
        BASE,
        importance=Importance.CRITICAL,
        due_at=NOW - timedelta(hours=1),
        estimated_minutes=1,
        course_code="PCC301COM",
        career_relevance=1.0,
    )
    assert 99 <= scorer.score(best, NOW).total <= 100
    worst = replace(BASE, importance=Importance.LOW, estimated_minutes=10_000)
    assert 0 <= scorer.score(worst, NOW).total < 10


def test_reasons_explain_the_biggest_contributors_first(scorer: Prioritizer) -> None:
    task = replace(
        BASE, due_at=NOW + timedelta(hours=20), course_code="PCC301COM", importance=Importance.HIGH
    )
    reasons = scorer.score(task, NOW).top_reasons()
    assert reasons[0].startswith("Due in 20h")
    assert any("Artificial Intelligence" in r for r in reasons)


def test_naive_datetimes_are_refused(scorer: Prioritizer) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        scorer.score(BASE, NOW.replace(tzinfo=None))
