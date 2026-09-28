"""`meow doctor`: real checks, each with a concrete fix. Nothing here pretends."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import ValidationError

from meow.config import Settings, load_profile
from meow.db.engine import current_revision, head_revision, make_engine, make_session_factory
from meow.domain.schedule import WeeklySchedule
from meow.integrations.google.auth import KeychainTokenStore, TokenStore
from meow.llm.ollama import LLMError, OllamaClient
from meow.security import token_source
from meow.services import accounts


class Status(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: Status
    detail: str
    fix: str = ""


def run_checks(
    settings: Settings,
    ollama_factory: Callable[[str, float], OllamaClient] | None = None,
    token_store: TokenStore | None = None,
) -> list[Check]:
    checks: list[Check] = []

    # Data directory
    try:
        settings.ensure_home()
        writable = os.access(settings.home, os.W_OK)
    except OSError as exc:
        writable, err = False, str(exc)
    else:
        err = "not writable"
    checks.append(
        Check("Data directory", Status.OK, str(settings.home))
        if writable
        else Check(
            "Data directory",
            Status.FAIL,
            f"{settings.home}: {err}",
            "Set MEOW_HOME to a writable folder",
        )
    )

    # Config
    try:
        profile = load_profile(settings.config_file)
    except (ValidationError, ValueError, OSError) as exc:
        first = str(exc).splitlines()[:3]
        checks.append(Check("Config", Status.FAIL, " ".join(first), f"Fix {settings.config_file}"))
        return checks
    source = str(settings.config_file) if settings.config_file.exists() else "defaults only"
    checks.append(Check("Config", Status.OK, f"valid ({source})"))

    # Schedule
    schedule = WeeklySchedule(profile.schedule, profile.user.tz)
    overlaps = schedule.overlaps()
    if overlaps:
        a, b = overlaps[0]
        checks.append(
            Check(
                "Schedule",
                Status.FAIL,
                f"'{a.block.name}' overlaps '{b.block.name}' on {a.day:%a}",
                "Adjust [[schedule]] times in your config",
            )
        )
    else:
        checks.append(
            Check(
                "Schedule",
                Status.OK,
                f"{schedule.weekly_focus_hours():.1f} h of focus time per week, "
                f"planner caps at {profile.planner.max_focus_hours_per_day:g} h/day",
            )
        )

    # Database
    if not settings.db_path.exists():
        checks.append(
            Check(
                "Database",
                Status.WARN,
                "not created yet",
                "Run `meow db upgrade` (or just `meow serve`)",
            )
        )
    else:
        engine = make_engine(settings.db_path)
        try:
            current, head = current_revision(engine), head_revision()
        finally:
            engine.dispose()
        if current == head:
            checks.append(Check("Database", Status.OK, f"schema up to date ({head})"))
        else:
            checks.append(
                Check(
                    "Database",
                    Status.WARN,
                    f"schema at {current}, latest is {head}",
                    "Run `meow db upgrade`",
                )
            )

    # API token
    src = token_source(settings)
    if src == "keychain":
        checks.append(Check("API token", Status.OK, "stored in the macOS Keychain"))
    elif src == "environment":
        checks.append(Check("API token", Status.OK, "from MEOW_API_TOKEN"))
    elif src == "file":
        checks.append(
            Check(
                "API token",
                Status.WARN,
                f"stored in {settings.token_file}",
                "Keychain was unavailable; the file is readable only by you",
            )
        )
    else:
        checks.append(
            Check(
                "API token",
                Status.WARN,
                "not created yet",
                "Created automatically on first `meow serve`",
            )
        )

    # Ollama
    make = ollama_factory or (lambda url, timeout: OllamaClient(url, timeout))
    client = make(profile.llm.base_url, 3.0)
    try:
        version = client.version()
        models = client.installed_models()
    except LLMError:
        checks.append(
            Check(
                "Ollama",
                Status.FAIL,
                f"not reachable at {profile.llm.base_url}",
                "Start it with `ollama serve` (or open the Ollama app)",
            )
        )
    else:
        checks.append(Check("Ollama", Status.OK, f"running, version {version}"))
        wanted = profile.llm.extract_model
        have = any(m == wanted or m == f"{wanted}:latest" for m in models)
        checks.append(
            Check("Extraction model", Status.OK, f"{wanted} installed")
            if have
            else Check(
                "Extraction model",
                Status.FAIL,
                f"{wanted} is not installed",
                f"Run `ollama pull {wanted}`",
            )
        )
    finally:
        client.close()

    checks += google_checks(settings, token_store)
    return checks


def google_checks(settings: Settings, token_store: TokenStore | None = None) -> list[Check]:
    checks: list[Check] = []
    client = settings.google_client_file
    if client.exists():
        checks.append(Check("Google client", Status.OK, "OAuth client installed"))
    else:
        checks.append(
            Check(
                "Google client",
                Status.WARN,
                "not installed",
                "Run `meow google setup ~/Downloads/credentials.json`",
            )
        )
    if not settings.db_path.exists():
        return checks
    store = token_store or KeychainTokenStore(settings)
    engine = make_engine(settings.db_path)
    try:
        if current_revision(engine) != head_revision():
            return checks
        with make_session_factory(engine)() as db:
            rows = accounts.list_accounts(db, enabled_only=True)
            if not rows:
                checks.append(
                    Check(
                        "Google accounts",
                        Status.WARN,
                        "none connected",
                        "Run `meow google login you@gmail.com`",
                    )
                )
            for acct in rows:
                name = f"Google: {acct.email}"
                if store.load(acct.email) is None:
                    checks.append(
                        Check(
                            name,
                            Status.FAIL,
                            "no token stored",
                            f"Run `meow google login {acct.email}`",
                        )
                    )
                elif acct.needs_reauth:
                    checks.append(
                        Check(
                            name,
                            Status.FAIL,
                            acct.last_error or "sign-in expired",
                            f"Run `meow google login {acct.email}`",
                        )
                    )
                else:
                    failing = [st for st in accounts.sync_states(db, acct.email) if st.last_error]
                    if failing:
                        st = failing[0]
                        checks.append(
                            Check(
                                name,
                                Status.WARN,
                                f"{st.source.value}: {st.last_error}",
                                "Run `meow sync` to retry",
                            )
                        )
                    else:
                        synced = ", ".join(acct.sources)
                        checks.append(Check(name, Status.OK, f"connected ({synced})"))
    finally:
        engine.dispose()
    return checks
