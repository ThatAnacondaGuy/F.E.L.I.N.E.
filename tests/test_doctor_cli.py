from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from meow.cli import app, parse_when
from meow.config import Profile, Settings
from meow.doctor import Status, run_checks
from meow.llm.ollama import OllamaClient

from support import ist


def fake_ollama(models: list[str] | None) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        if models is None:
            raise httpx.ConnectError("refused")
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.31.1"})
        return httpx.Response(200, json={"models": [{"name": m} for m in models]})

    return lambda url, timeout: OllamaClient(url, timeout, transport=httpx.MockTransport(handler))


def by_name(checks: list) -> dict:  # type: ignore[type-arg]
    return {c.name: c for c in checks}


def test_doctor_reports_ollama_down_with_a_fix(settings: Settings) -> None:
    checks = by_name(run_checks(settings, fake_ollama(None)))  # type: ignore[arg-type]
    assert checks["Ollama"].status is Status.FAIL
    assert "ollama serve" in checks["Ollama"].fix
    assert checks["Config"].status is Status.OK
    assert checks["Schedule"].status is Status.OK


def test_doctor_names_the_missing_model(settings: Settings) -> None:
    checks = by_name(run_checks(settings, fake_ollama(["llama3.2:1b"])))  # type: ignore[arg-type]
    assert checks["Ollama"].status is Status.OK
    assert checks["Extraction model"].status is Status.FAIL
    assert checks["Extraction model"].fix == "Run `ollama pull qwen3:8b`"


def test_doctor_all_green_when_ready(settings: Settings) -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["db", "upgrade"]).exit_code == 0
    checks = by_name(run_checks(settings, fake_ollama(["qwen3:8b"])))  # type: ignore[arg-type]
    assert checks["Database"].status is Status.OK
    assert checks["Extraction model"].status is Status.OK
    assert checks["API token"].detail == "from MEOW_API_TOKEN"


def test_doctor_catches_a_broken_user_config(settings: Settings) -> None:
    settings.ensure_home()
    settings.config_file.write_text("[scoring.weights]\nurgency = 5\n")
    checks = by_name(run_checks(settings, fake_ollama(None)))  # type: ignore[arg-type]
    assert checks["Config"].status is Status.FAIL


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-10-02 18:30", ist(2026, 10, 2, 18, 30)),
        ("2026-10-02", ist(2026, 10, 2, 23, 59)),
        ("today 21:00", ist(2026, 9, 28, 21, 0)),
        ("tomorrow", ist(2026, 9, 29, 23, 59)),
        ("fri", ist(2026, 10, 2, 23, 59)),
        ("friday 17:00", ist(2026, 10, 2, 17, 0)),
        ("mon 20:00", ist(2026, 9, 28, 20, 0)),  # later today (it's Monday 18:00)
        ("mon 09:00", ist(2026, 10, 5, 9, 0)),  # already passed today, so next week
    ],
)
def test_parse_when(profile: Profile, text: str, expected: object) -> None:
    assert parse_when(text, profile, now=ist(2026, 9, 28, 18, 0)) == expected


def test_cli_task_add_list_and_plan() -> None:
    runner = CliRunner()
    r = runner.invoke(
        app,
        [
            "task",
            "add",
            "Revise TOC pumping lemma",
            "--minutes",
            "45",
            "--course",
            "PCC303COM",
            "--due",
            "tomorrow 23:00",
        ],
    )
    assert r.exit_code == 0, r.output
    listing = runner.invoke(app, ["task", "list"], env={"COLUMNS": "200"})
    assert "Revise TOC pumping lemma" in listing.output
    assert "Due in 1d" in listing.output  # the reasons are shown, biggest first
    assert runner.invoke(app, ["plan"]).exit_code == 0


def test_cli_rejects_unknown_course() -> None:
    r = CliRunner().invoke(app, ["task", "add", "x", "--course", "NOPE"])
    assert r.exit_code == 1 and "Unknown course" in r.output


def test_parse_when_rejects_garbage(profile: Profile) -> None:
    import typer

    with pytest.raises(typer.BadParameter):
        parse_when("next blue moon", profile)


# ── Google ───────────────────────────────────────────────────────────────


def test_google_setup_installs_the_client(settings: Settings, tmp_path: Path) -> None:
    src = tmp_path / "credentials.json"
    src.write_text(json.dumps({"installed": {"client_id": "x", "client_secret": "y"}}))
    r = CliRunner().invoke(app, ["google", "setup", str(src)])
    assert r.exit_code == 0, r.output
    assert settings.google_client_file.exists()


def test_google_login_rejects_unknown_sources() -> None:
    r = CliRunner().invoke(app, ["google", "login", "me@gmail.test", "--sources", "manual"])
    assert r.exit_code != 0 and "choose from" in r.output


def test_sync_without_accounts_explains_what_to_do() -> None:
    r = CliRunner().invoke(app, ["sync", "--no-extract"], env={"COLUMNS": "200"})
    assert r.exit_code == 1 and "meow google login" in r.output
    r = CliRunner().invoke(app, ["google", "accounts"], env={"COLUMNS": "200"})
    assert r.exit_code == 0 and "No accounts yet" in r.output


def test_doctor_google_checks(settings: Settings) -> None:
    from meow.db.engine import make_engine, make_session_factory, upgrade
    from meow.doctor import google_checks
    from meow.services import accounts
    from meow.types import SourceKind

    from support import MemoryTokenStore

    settings.ensure_home()
    engine = make_engine(settings.db_path)
    upgrade(engine)
    with make_session_factory(engine)() as db:
        accounts.connect(db, "me@gmail.test", [SourceKind.GMAIL])
    engine.dispose()

    missing = by_name(google_checks(settings, MemoryTokenStore()))
    assert missing["Google client"].status is Status.WARN
    assert missing["Google: me@gmail.test"].status is Status.FAIL
    assert "no token" in missing["Google: me@gmail.test"].detail

    ok = by_name(google_checks(settings, MemoryTokenStore({"me@gmail.test": "{}"})))
    assert ok["Google: me@gmail.test"].status is Status.OK


def test_brief_prints_todays_briefing() -> None:
    runner = CliRunner()
    runner.invoke(app, ["task", "add", "Revise TOC", "--due", "tomorrow 23:00", "--minutes", "45"])
    r = runner.invoke(app, ["brief", "morning"], env={"COLUMNS": "200"})
    assert r.exit_code == 0, r.output
    assert "Morning briefing" in r.output and "Revise TOC" in r.output
