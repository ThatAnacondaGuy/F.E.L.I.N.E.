from __future__ import annotations

from meow.config import Profile
from meow.evals.extraction import SEED_PATH, Case, load_cases, run_eval, summarise
from meow.llm.extraction import Extractor

from support import FakeLLM, extracted


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
