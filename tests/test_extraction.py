from __future__ import annotations

import httpx
import pytest
from sqlalchemy.orm import Session

from meow.config import Profile
from meow.db.models import AuditEntry, Proposal, SourceItem
from meow.llm.extraction import (
    ExtractionError,
    ExtractionOutput,
    Extractor,
    SourceText,
    evidence_in_source,
)
from meow.llm.ollama import LLMError, OllamaClient
from meow.services import capture
from meow.types import ProposalStatus

from support import LAB_EMAIL, FakeLLM, extracted, ist

NOW = ist(2026, 9, 28, 18, 0)
SOURCE = SourceText(
    body=LAB_EMAIL, title="CN Lab 4", author="prof@college.edu", occurred_at=NOW, kind="gmail"
)


def run(profile: Profile, *items: dict[str, object]) -> tuple[FakeLLM, object]:
    llm = FakeLLM({"tasks": list(items)})
    return llm, Extractor(llm, profile).extract(SOURCE, NOW)


def test_well_supported_task_becomes_a_candidate(profile: Profile) -> None:
    _, report = run(profile, extracted())
    (cand,) = report.candidates  # type: ignore[attr-defined]
    assert cand.draft.title == "Submit CN lab assignment 4"
    assert cand.draft.due_at == ist(2026, 10, 2, 23, 59)  # local time, interpreted in IST
    assert cand.draft.course_code == "PCC302COM"
    assert cand.confidence == 0.9


def test_hallucinated_evidence_is_dropped(profile: Profile) -> None:
    _, report = run(profile, extracted(evidence="Register for the NVIDIA hackathon by Monday"))
    assert report.candidates == []  # type: ignore[attr-defined]
    assert report.dropped == [  # type: ignore[attr-defined]
        ("Submit CN lab assignment 4", "evidence quote not found in the source")
    ]


@pytest.mark.parametrize(
    "quote",
    [
        "submit   lab assignment 4 by friday 11:59 pm",  # case and whitespace
        "Submit lab assignment 4 … Late submissions will not be accepted.",  # ellipsis
        "“Submit lab assignment 4 by Friday 11:59 PM”",  # smart quotes around it
    ],
)
def test_evidence_matching_tolerates_formatting(quote: str) -> None:
    assert evidence_in_source(quote, LAB_EMAIL)


def test_evidence_matching_rejects_empty_quotes() -> None:
    assert not evidence_in_source("  ...  ", LAB_EMAIL)


def test_unknown_course_is_cleared_not_trusted(profile: Profile) -> None:
    _, report = run(profile, extracted(course_code="CS999"))
    (cand,) = report.candidates  # type: ignore[attr-defined]
    assert cand.draft.course_code is None
    assert "unknown course 'CS999'" in cand.notes


def test_deadline_the_text_does_not_state_is_removed(profile: Profile) -> None:
    # qwen3 once gave a resume request the send time as its "deadline".
    _, report = run(profile, extracted(due="2026-09-28T12:00", due_phrase=None))
    (cand,) = report.candidates  # type: ignore[attr-defined]
    assert cand.draft.due_at is None
    assert "removed a deadline the text doesn't state" in cand.notes


def test_asks_whose_deadline_had_already_passed_are_dropped(profile: Profile) -> None:
    body = "The deadline for the IPR assignment was last Friday; late work is not accepted."
    llm = FakeLLM(
        {
            "tasks": [
                extracted(
                    title="Submit IPR assignment",
                    evidence=body,
                    due_phrase="last Friday",
                    due="2026-09-25T23:59",
                )
            ]
        }
    )
    report = Extractor(llm, profile).extract(SourceText(body=body, occurred_at=NOW), NOW)
    assert report.candidates == []
    assert report.dropped == [
        ("Submit IPR assignment", "its deadline had already passed when the message was sent")
    ]


def test_unreadable_deadline_lowers_confidence(profile: Profile) -> None:
    _, report = run(profile, extracted(due="next Friday-ish", due_phrase=None))
    (cand,) = report.candidates  # type: ignore[attr-defined]
    assert cand.draft.due_at is None and cand.confidence == 0.45


def test_wrong_weekday_from_the_model_is_corrected(profile: Profile) -> None:
    # The real qwen3:8b put "this Friday" on Wednesday; code reads the phrase instead.
    _, report = run(profile, extracted(due="2026-09-30T23:59"))
    (cand,) = report.candidates  # type: ignore[attr-defined]
    assert cand.draft.due_at == ist(2026, 10, 2, 23, 59)
    assert "deadline corrected from Wed 30 Sep 23:59" in cand.notes[0]


def test_phrase_without_a_time_keeps_the_models_time(profile: Profile) -> None:
    llm = FakeLLM(
        {
            "tasks": [
                extracted(
                    evidence="Late submissions will not be accepted.",
                    due_phrase="Friday",
                    due="2026-10-01T09:15",
                )
            ]
        }
    )
    source = SourceText(body=LAB_EMAIL, occurred_at=NOW)
    (cand,) = Extractor(llm, profile).extract(source, NOW).candidates
    assert cand.draft.due_at == ist(2026, 10, 2, 9, 15)


def test_phrase_not_in_the_source_removes_the_deadline(profile: Profile) -> None:
    # qwen3 copied "by this Friday, 5 PM" from the prompt's example into an email without one.
    _, report = run(profile, extracted(due_phrase="by this Friday, 5 PM"))
    (cand,) = report.candidates  # type: ignore[attr-defined]
    assert cand.draft.due_at is None


def test_coursework_career_value_comes_from_your_settings(profile: Profile) -> None:
    # The model rated a Computer Networks lab 0.6 for the NVIDIA goal; your config says 0.
    _, report = run(profile, extracted(career_relevance=0.6))
    assert report.candidates[0].draft.career_relevance == 0.0  # type: ignore[attr-defined]
    _, report = run(profile, extracted(course_code=None, career_relevance=0.9))
    assert report.candidates[0].draft.career_relevance == 0.9  # type: ignore[attr-defined]


def test_prompt_includes_a_calendar_from_the_sent_date(profile: Profile) -> None:
    llm, _ = run(profile)
    system = llm.calls[0]["system"]
    assert "- Monday 28 September 2026 (the day it was sent)" in system
    assert "- Friday 02 October 2026" in system
    assert "use 09:15" in system


def test_off_schema_output_is_an_error_not_a_guess(profile: Profile) -> None:
    llm = FakeLLM({"tasks": [{"title": "only a title"}]})
    with pytest.raises(ExtractionError, match="schema"):
        Extractor(llm, profile).extract(SOURCE, NOW)


def test_prompt_carries_time_courses_and_goal(profile: Profile) -> None:
    llm, _ = run(profile)
    call = llm.calls[0]
    assert "Monday 2026-09-28 18:00" in call["system"]
    assert "PCC301COM: Artificial Intelligence" in call["system"]
    assert "NVIDIA" in call["system"]
    assert "From: prof@college.edu" in call["user"]
    assert call["model"] == profile.llm.extract_model
    assert call["schema"] == ExtractionOutput.model_json_schema()


# ── capture service (source → proposals) ─────────────────────────────────


def test_capture_files_proposals_with_evidence(db: Session, profile: Profile) -> None:
    llm = FakeLLM({"tasks": [extracted(), extracted(title="Fake", evidence="not in there")]})
    result = capture.capture_text(db, profile, Extractor(llm, profile), LAB_EMAIL, now=NOW)
    (p,) = result.proposals
    assert p.status is ProposalStatus.PENDING and p.evidence and p.source_item_id
    assert len(result.dropped) == 1
    assert db.query(AuditEntry).filter_by(action="extraction.dropped").count() == 1


def test_capturing_the_same_text_twice_does_not_duplicate(db: Session, profile: Profile) -> None:
    llm = FakeLLM({"tasks": [extracted()]})
    extractor = Extractor(llm, profile)
    capture.capture_text(db, profile, extractor, LAB_EMAIL, now=NOW)
    again = capture.capture_text(db, profile, extractor, LAB_EMAIL, now=NOW)
    assert again.duplicate
    assert len(llm.calls) == 1
    assert db.query(Proposal).count() == 1


def test_failed_extraction_keeps_the_source_for_retry(db: Session, profile: Profile) -> None:
    def boom(_: str) -> object:
        raise LLMError("Ollama unreachable")

    with pytest.raises(ExtractionError):
        capture.capture_text(db, profile, Extractor(FakeLLM(boom), profile), LAB_EMAIL, now=NOW)
    item = db.query(SourceItem).one()
    assert item.extraction_error and item.extracted_at is None

    ok = capture.capture_text(
        db, profile, Extractor(FakeLLM({"tasks": [extracted()]}), profile), LAB_EMAIL, now=NOW
    )
    assert not ok.duplicate and len(ok.proposals) == 1


# ── Ollama client against a fake HTTP server ─────────────────────────────


def ollama(handler: object) -> OllamaClient:
    return OllamaClient("http://ollama.test", transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_client_sends_schema_and_parses_json() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": '{"tasks": []}'}})

    assert ollama(handler).chat_json("m", "sys", "usr", {"type": "object"}) == {"tasks": []}
    assert seen["format"] == {"type": "object"}
    assert seen["options"] == {"temperature": 0} and seen["stream"] is False


def test_client_explains_missing_models() -> None:
    client = ollama(lambda r: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(LLMError, match="ollama pull qwen3:8b"):
        client.chat_json("qwen3:8b", "s", "u", {})


def test_client_rejects_non_json_content() -> None:
    client = ollama(lambda r: httpx.Response(200, json={"message": {"content": "Sure! Here"}}))
    with pytest.raises(LLMError, match="invalid JSON"):
        client.chat_json("m", "s", "u", {})


def test_client_sends_think_only_when_configured() -> None:
    import json

    sent: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "{}"}})

    transport = httpx.MockTransport(handler)
    OllamaClient("http://ollama.test", transport=transport).chat_json("m", "s", "u", {})
    OllamaClient("http://ollama.test", transport=transport, think=False).chat_json(
        "m", "s", "u", {}
    )
    assert "think" not in sent[0] and sent[1]["think"] is False


def test_task_wording_offered_as_a_deadline_is_not_a_deadline(profile: Profile) -> None:
    body = "Also, form groups of 3 for the mini project."
    llm = FakeLLM(
        {
            "tasks": [
                extracted(
                    evidence=body,
                    due_phrase="form groups of 3 for the mini project",
                    due="2026-09-28T23:59",
                    course_code=None,
                )
            ]
        }
    )
    (cand,) = (
        Extractor(llm, profile).extract(SourceText(body=body, occurred_at=NOW), NOW).candidates
    )
    assert cand.draft.due_at is None


def test_unparseable_but_real_time_wording_keeps_the_models_date(profile: Profile) -> None:
    body = "bhai kal tak CC ka assignment 2 submit karna hai, sir ne bola 5 baje tak"
    llm = FakeLLM(
        {
            "tasks": [
                extracted(
                    evidence=body,
                    due_phrase="kal tak ... 5 baje tak",
                    due="2026-09-29T17:00",
                    course_code="PEC321BCOM",
                )
            ]
        }
    )
    (cand,) = (
        Extractor(llm, profile).extract(SourceText(body=body, occurred_at=NOW), NOW).candidates
    )
    assert cand.draft.due_at == ist(2026, 9, 29, 17, 0)
