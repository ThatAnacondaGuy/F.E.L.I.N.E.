from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from meow.config import Profile, Settings
from meow.evals.extraction import SEED_PATH, Case, load_cases, run_eval, summarise
from meow.llm.extraction import Extractor

from support import LAB_EMAIL, FakeLLM, extracted, ist


def test_seed_benchmark_loads_and_has_negatives() -> None:
    cases = load_cases(SEED_PATH)
    assert len(cases) == 23
    assert sum(1 for c in cases if not c.expected) == 4


def test_perfect_model_scores_full_marks(profile: Profile) -> None:
    case = Case.model_validate(
        {
            "id": "lab",
            "sent": "2026-09-28T18:00:00+05:30",
            "body": "Dear students,\n\nSubmit lab assignment 4 by Friday 11:59 PM on the portal.",
            "expected": [
                {"anchor": ["lab assignment 4"], "due": "2026-10-02T23:59", "course": "PCC302COM"}
            ],
        }
    )
    llm = FakeLLM({"tasks": [extracted(evidence="Submit lab assignment 4 by Friday 11:59 PM")]})
    s = summarise(run_eval([case], Extractor(llm, profile), profile), "fake", None)
    assert (s.precision, s.recall, s.deadline_accuracy, s.course_accuracy) == (1, 1, 1, 1)


def test_false_positive_on_a_negative_and_optional_items(profile: Profile) -> None:
    negative = Case.model_validate(
        {
            "id": "promo",
            "sent": "2026-09-28T09:00:00+05:30",
            "body": "Submit lab assignment 4 by Friday 11:59 PM",
        }
    )
    optional = Case.model_validate(
        {
            "id": "opt",
            "sent": "2026-09-28T09:00:00+05:30",
            "body": "Submit lab assignment 4 by Friday 11:59 PM",
            "expected": [{"anchor": ["nothing like this"], "optional": True}],
        }
    )
    llm = FakeLLM({"tasks": [extracted(evidence="Submit lab assignment 4 by Friday 11:59 PM")]})
    results = run_eval([negative, optional], Extractor(llm, profile), profile)
    s = summarise(results, "fake", None)
    assert s.clean_negatives == "0/1"
    assert results[1].expected == 0  # a missed optional item is not held against the model
    assert s.precision == 0.0


def test_export_uses_your_decisions_as_ground_truth(db: Session, profile: Profile) -> None:
    from meow.evals.extraction import cases_from_decisions
    from meow.services import capture, proposals

    two_tasks = FakeLLM(
        {
            "tasks": [
                extracted(),
                extracted(
                    title="Fake",
                    evidence="Late submissions will not be accepted.",
                    due_phrase=None,
                    due=None,
                ),
            ]
        }
    )
    result = capture.capture_text(
        db, profile, Extractor(two_tasks, profile), LAB_EMAIL, now=ist(2026, 9, 28, 18, 0)
    )
    real, fake = result.proposals
    proposals.approve(db, profile, real.id, edits={"due_at": "2026-10-02T17:00:00+05:30"})
    proposals.reject(db, profile, fake.id, reason="not a task")

    (case,) = cases_from_decisions(db, profile)
    (task,) = case.expected  # the rejected one is not expected
    assert task.due == "2026-10-02T17:00"  # your edit, not the model's answer
    assert task.anchor == ["Submit lab assignment 4 by Friday"]
    assert case.body == LAB_EMAIL and "mine" in case.tags


def test_export_skips_sources_you_have_not_fully_decided(db: Session, profile: Profile) -> None:
    from meow.evals.extraction import cases_from_decisions
    from meow.services import capture

    capture.capture_text(
        db,
        profile,
        Extractor(FakeLLM({"tasks": [extracted()]}), profile),
        LAB_EMAIL,
        now=ist(2026, 9, 28, 18, 0),
    )
    assert cases_from_decisions(db, profile) == []  # still pending


def test_eval_run_command(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    from typer.testing import CliRunner

    import meow.cli

    monkeypatch.setattr(meow.cli, "OllamaClient", lambda *a, **k: _ClosingFake({"tasks": []}))
    r = CliRunner().invoke(
        meow.cli.app,
        ["eval", "run", "--case", "newsletter", "--case", "promo"],
        env={"COLUMNS": "200"},
    )
    assert r.exit_code == 0, r.output
    assert "2/2" in r.output  # both negatives stayed clean
    reports = list((settings.home / "evals" / "reports").glob("*.json"))
    assert len(reports) == 1


class _ClosingFake(FakeLLM):
    def close(self) -> None:
        pass
