"""The `meow` command. Works directly on the local database; the server is optional."""

from __future__ import annotations

import sys
import time
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from sqlalchemy.orm import Session

from meow import __version__
from meow.config import Profile, Settings
from meow.db.engine import make_engine, make_session_factory, upgrade
from meow.db.models import Proposal, Task
from meow.doctor import Status, run_checks
from meow.domain.timeutil import utcnow
from meow.integrations.google.auth import (
    GOOGLE_SOURCES,
    GoogleAuthError,
    KeychainTokenStore,
    install_client_file,
    run_login_flow,
)
from meow.llm.extraction import ExtractionError, Extractor
from meow.llm.ollama import OllamaClient
from meow.security import load_or_create_token, login_code
from meow.services import accounts, capture, proposals, syncing, tasks
from meow.types import Category, Importance, ProposalStatus, SourceKind, TaskStatus

app = typer.Typer(
    help="Meow OS: your local-first chief of staff.", no_args_is_help=True, add_completion=False
)
db_app = typer.Typer(help="Database maintenance.", no_args_is_help=True)
task_app = typer.Typer(help="Manage tasks.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(task_app, name="task")
google_app = typer.Typer(
    help="Connect Google accounts (Gmail, Calendar, Classroom).", no_args_is_help=True
)
app.add_typer(google_app, name="google")
console = Console()

WEEKDAYS = {
    "mon": "monday",
    "tue": "tuesday",
    "wed": "wednesday",
    "thu": "thursday",
    "fri": "friday",
    "sat": "saturday",
    "sun": "sunday",
}
WEEKDAY_INDEX = {name: i for i, name in enumerate(WEEKDAYS)}


@contextmanager
def _session(settings: Settings) -> Iterator[Session]:
    settings.ensure_home()
    engine = make_engine(settings.db_path)
    upgrade(engine)
    try:
        with make_session_factory(engine)() as db:
            yield db
    finally:
        engine.dispose()


def parse_when(text: str, profile: Profile, now: datetime | None = None) -> datetime:
    """'2026-10-02 23:59', '2026-10-02', 'today 18:00', 'tomorrow', 'fri', 'friday 17:00'.

    A missing time means 23:59. A weekday means its next occurrence, today included if
    that time is still ahead.
    """
    tz = profile.user.tz
    local_now = (now or utcnow()).astimezone(tz)
    words = text.strip().lower().split()
    if not words:
        raise typer.BadParameter("empty date")
    clock = words[1] if len(words) > 1 else "23:59"
    day = None
    if words[0] in ("today", "tomorrow"):
        day = local_now.date() + timedelta(days=1 if words[0] == "tomorrow" else 0)
    elif words[0][:3] in WEEKDAYS and WEEKDAYS[words[0][:3]].startswith(words[0]):
        ahead = (WEEKDAY_INDEX[words[0][:3]] - local_now.weekday()) % 7
        day = local_now.date() + timedelta(days=ahead)
    try:
        if day is not None:
            moment = datetime.fromisoformat(f"{day.isoformat()}T{clock}").replace(tzinfo=tz)
            return moment + timedelta(days=7) if moment <= local_now else moment
        value = text.strip().replace(" ", "T", 1)
        if len(value) == 10:
            value += "T23:59"
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"can't read date {text!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)


def _find_proposal(db: Session, prefix: str) -> Proposal:
    matches = list(db.scalars(select(Proposal).where(Proposal.id.startswith(prefix))))
    if len(matches) != 1:
        console.print(f"[red]{'No' if not matches else 'Several'} proposals match {prefix!r}.[/]")
        raise typer.Exit(1)
    return matches[0]


# ── system ───────────────────────────────────────────────────────────────


@app.command()
def version() -> None:
    """Print the version."""
    console.print(__version__)


@app.command()
def doctor() -> None:
    """Check that everything Meow needs is really there."""
    checks = run_checks(Settings())
    icon = {Status.OK: "[green]✓[/]", Status.WARN: "[yellow]![/]", Status.FAIL: "[red]✗[/]"}
    table = Table(show_header=False, box=None, padding=(0, 1))
    for c in checks:
        table.add_row(
            icon[c.status], f"[bold]{c.name}[/]", c.detail, f"[dim]{c.fix}[/]" if c.fix else ""
        )
    console.print(table)
    if any(c.status is Status.FAIL for c in checks):
        raise typer.Exit(1)


@app.command()
def config() -> None:
    """Show where Meow keeps its files."""
    s = Settings()
    console.print(f"Data directory: {s.home}")
    console.print(
        f"Your config:    {s.config_file} "
        f"{'(exists)' if s.config_file.exists() else '(not created; defaults apply)'}"
    )
    console.print(f"Database:       {s.db_path}")


@app.command()
def serve(reload: Annotated[bool, typer.Option(help="Restart on code changes.")] = False) -> None:
    """Run the local server (dashboard + API)."""
    import uvicorn

    profile = Settings().profile
    console.print(
        f"Meow OS on http://{profile.server.host}:{profile.server.port}. "
        "Run [bold]meow open[/] in another terminal to sign in."
    )
    uvicorn.run(
        "meow.api.app:create_app_from_env",
        factory=True,
        host=profile.server.host,
        port=profile.server.port,
        reload=reload,
        log_level="info",
    )


@app.command("open")
def open_dashboard() -> None:
    """Open the dashboard in your browser, signed in (the link expires in 2 minutes)."""
    settings = Settings()
    profile = settings.profile
    token = load_or_create_token(settings)
    ts = int(time.time())
    url = f"http://127.0.0.1:{profile.server.port}/login?code={login_code(token, ts)}&ts={ts}"
    webbrowser.open(url)
    console.print("Opened the dashboard. If nothing appeared, is [bold]meow serve[/] running?")


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Apply pending schema migrations."""
    settings = Settings()
    settings.ensure_home()
    engine = make_engine(settings.db_path)
    upgrade(engine)
    engine.dispose()
    console.print(f"Database ready at {settings.db_path}")


# ── tasks & planning ─────────────────────────────────────────────────────


@task_app.command("add")
def task_add(
    title: str,
    due: Annotated[
        str | None, typer.Option(help="e.g. '2026-10-02 23:59', 'tomorrow 18:00'")
    ] = None,
    minutes: Annotated[int | None, typer.Option(help="Estimated minutes of work")] = None,
    importance: Importance = Importance.MEDIUM,
    category: Category = Category.ACADEMIC,
    course: Annotated[str | None, typer.Option(help="Course code, e.g. PCC301COM")] = None,
    career: Annotated[float, typer.Option(min=0, max=1, help="Career relevance 0-1")] = 0.0,
) -> None:
    """Add a task directly."""
    settings = Settings()
    profile = settings.profile
    if course and profile.course(course) is None:
        codes = ", ".join(c.code for c in profile.courses)
        console.print(f"[red]Unknown course {course!r}.[/] Known: {codes}")
        raise typer.Exit(1)
    draft = tasks.TaskDraft(
        title=title,
        due_at=parse_when(due, profile) if due else None,
        estimated_minutes=minutes,
        importance=importance,
        category=category,
        course_code=course,
        career_relevance=career,
    )
    with _session(settings) as db:
        task = tasks.add_task(db, draft)
        console.print(f"Added [bold]{task.title}[/] ({task.id[:8]})")


@task_app.command("list")
def task_list() -> None:
    """Open tasks, highest priority first, with the reasons."""
    settings = Settings()
    profile = settings.profile
    now = utcnow()
    with _session(settings) as db:
        ranked = tasks.ranked_tasks(db, profile, now)
    if not ranked:
        console.print("No open tasks.")
        return
    table = Table("Score", "Task", "Due", "Why")
    tz = profile.user.tz
    for r in ranked:
        due = r.task.due_at.astimezone(tz).strftime("%a %d %b %H:%M") if r.task.due_at else "—"
        table.add_row(f"{r.score.total:.0f}", r.task.title, due, " · ".join(r.score.top_reasons()))
    console.print(table)


@task_app.command("done")
def task_done(task_id: str) -> None:
    """Mark a task done (ID prefix is enough)."""
    with _session(Settings()) as db:
        matches = list(db.scalars(select(Task).where(Task.id.startswith(task_id))))
        if len(matches) != 1:
            console.print(f"[red]{len(matches)} tasks match {task_id!r}.[/]")
            raise typer.Exit(1)
        task = tasks.set_status(db, matches[0].id, TaskStatus.DONE, actor="user")
        console.print(f"Done: {task.title}")


@app.command()
def plan() -> None:
    """Show the plan for the coming days."""
    settings = Settings()
    profile = settings.profile
    tz = profile.user.tz
    with _session(settings) as db:
        result = tasks.build_plan(db, profile, utcnow())
    if not result.sessions and not result.shortfalls:
        console.print("Nothing to plan. Add a task with [bold]meow task add[/].")
        return
    table = Table("Day", "Time", "Task")
    for s in result.sessions:
        start, end = s.interval.start.astimezone(tz), s.interval.end.astimezone(tz)
        table.add_row(s.day.strftime("%a %d %b"), f"{start:%H:%M}–{end:%H:%M}", s.title)
    console.print(table)
    for short in result.shortfalls:
        colour = "red" if short.at_risk else "yellow"
        console.print(
            f"[{colour}]{'AT RISK' if short.at_risk else 'Deferred'}[/] "
            f"{short.title}: {short.reason}"
        )


# ── inbox ────────────────────────────────────────────────────────────────


@app.command("capture")
def capture_cmd(
    text: Annotated[
        str | None, typer.Argument(help="Text to capture; reads stdin if omitted")
    ] = None,
    title: str = "",
) -> None:
    """Extract tasks from any text (email, Classroom post, message) into proposals."""
    body = text if text is not None else sys.stdin.read()
    settings = Settings()
    profile = settings.profile
    llm = OllamaClient(profile.llm.base_url, **profile.llm.client_options())
    with console.status(f"Reading with {profile.llm.extract_model}…"), _session(settings) as db:
        try:
            result = capture.capture_text(db, profile, Extractor(llm, profile), body, title=title)
        except (ExtractionError, ValueError) as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from None
        finally:
            llm.close()
    if result.duplicate:
        console.print("Already captured; see [bold]meow inbox[/].")
    for p in result.proposals:
        console.print(f"[green]+[/] {p.id[:8]}  {p.summary}  [dim]({p.confidence:.0%})[/]")
    for title_, reason in result.dropped:
        console.print(f"[yellow]- dropped[/] {title_}: {reason}")
    if not result.proposals and not result.dropped:
        console.print("No tasks found in that text.")


@app.command()
def inbox() -> None:
    """Pending proposals."""
    with _session(Settings()) as db:
        pending = proposals.list_proposals(db, ProposalStatus.PENDING)
        if not pending:
            console.print("Inbox zero.")
            return
        for p in pending:
            console.print(f"[bold]{p.id[:8]}[/] [{p.authority_level.value}] {p.summary}")
            if p.evidence:
                console.print(f"         [dim]“{p.evidence}”[/]")


@app.command()
def approve(proposal_id: str) -> None:
    """Approve a proposal (ID prefix is enough)."""
    settings = Settings()
    with _session(settings) as db:
        p = proposals.approve(db, settings.profile, _find_proposal(db, proposal_id).id)
        console.print(f"Approved: {p.summary}")


@app.command()
def reject(proposal_id: str, reason: str = "") -> None:
    """Reject a proposal (ID prefix is enough)."""
    settings = Settings()
    with _session(settings) as db:
        p = proposals.reject(
            db, settings.profile, _find_proposal(db, proposal_id).id, reason=reason
        )
        console.print(f"Rejected: {p.summary}")


# ── Google & sync ────────────────────────────────────────────────────────


def _parse_sources(text: str) -> list[SourceKind]:
    try:
        sources = [SourceKind(part.strip()) for part in text.split(",") if part.strip()]
    except ValueError:
        sources = []
    if not sources or any(s not in GOOGLE_SOURCES for s in sources):
        allowed = ", ".join(s.value for s in GOOGLE_SOURCES)
        raise typer.BadParameter(f"choose from: {allowed}")
    return sources


@google_app.command("setup")
def google_setup(
    client_file: Annotated[Path, typer.Argument(help="The OAuth client JSON from Google Cloud")],
) -> None:
    """Install your Google OAuth client (the 'Desktop app' JSON from Google Cloud Console)."""
    settings = Settings()
    settings.ensure_home()
    try:
        target = install_client_file(settings, client_file.expanduser())
    except GoogleAuthError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from None
    console.print(f"Installed at {target} (readable only by you).")
    console.print("Next: [bold]meow google login you@gmail.com[/]")


@google_app.command("login")
def google_login(
    email: str,
    sources: Annotated[
        str, typer.Option(help="Comma-separated: gmail, calendar, classroom")
    ] = "gmail,calendar,classroom",
) -> None:
    """Connect a Google account (opens your browser for Google's consent screen)."""
    settings = Settings()
    chosen = _parse_sources(sources)
    try:
        email = accounts.normalize_email(email)
        run_login_flow(settings, email, chosen, KeychainTokenStore(settings))
    except (GoogleAuthError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from None
    with _session(settings) as db:
        accounts.connect(db, email, chosen)
    console.print(f"Connected [bold]{email}[/] for {', '.join(s.value for s in chosen)}.")
    console.print("Run [bold]meow sync[/] to fetch now (or leave [bold]meow serve[/] running).")


@google_app.command("accounts")
def google_accounts() -> None:
    """Connected accounts and how each source last synced."""
    settings = Settings()
    tz = settings.profile.user.tz
    with _session(settings) as db:
        rows = accounts.list_accounts(db)
        if not rows:
            console.print("No accounts yet. Run [bold]meow google login you@gmail.com[/].")
            return
        table = Table("Account", "Source", "Last success", "Status")
        for acct in rows:
            states = {st.source.value: st for st in accounts.sync_states(db, acct.email)}
            for source in acct.sources:
                st = states.get(source)
                when = (
                    st.last_success_at.astimezone(tz).strftime("%d %b %H:%M")
                    if st and st.last_success_at
                    else "never"
                )
                if not acct.enabled:
                    status = "[dim]disconnected[/]"
                elif acct.needs_reauth:
                    status = "[red]sign in again[/]"
                elif st and st.last_error:
                    status = f"[yellow]{st.last_error[:60]}[/]"
                else:
                    status = "[green]ok[/]"
                table.add_row(acct.email, source, when, status)
    console.print(table)


@google_app.command("logout")
def google_logout(email: str) -> None:
    """Disconnect an account and delete its token from the Keychain."""
    settings = Settings()
    with _session(settings) as db:
        try:
            acct = accounts.disconnect(db, email)
        except (accounts.AccountNotFound, ValueError):
            console.print(f"[red]No connected account {email!r}.[/]")
            raise typer.Exit(1) from None
        KeychainTokenStore(settings).delete(acct.email)
    console.print(f"Disconnected {acct.email}. Its data already in Meow stays until you remove it.")


@app.command("sync")
def sync_cmd(
    account: Annotated[str | None, typer.Option(help="Only this account")] = None,
    source: Annotated[str | None, typer.Option(help="Only gmail, calendar or classroom")] = None,
    extract: Annotated[bool, typer.Option(help="Let the local model read new items")] = True,
) -> None:
    """Fetch new email, calendar events and Classroom work now."""
    settings = Settings()
    profile = settings.profile
    only = _parse_sources(source)[0] if source else None
    llm = OllamaClient(profile.llm.base_url, **profile.llm.client_options()) if extract else None
    try:
        with console.status("Syncing…"), _session(settings) as db:
            if not accounts.list_accounts(db, enabled_only=True):
                console.print("No accounts yet. Run [bold]meow google login you@gmail.com[/].")
                raise typer.Exit(1)
            run = syncing.run_sync(db, settings, utcnow(), llm=llm, account=account, source=only)
    except syncing.SyncBusy as exc:
        console.print(f"[yellow]{exc}[/]")
        raise typer.Exit(1) from None
    finally:
        if llm:
            llm.close()
    table = Table("Account", "Source", "New", "Proposals", "Problem")
    for r in run.google.results:
        table.add_row(
            r.account,
            r.source.value,
            str(r.new_items),
            str(r.proposals),
            f"[red]{r.error}[/]" if r.error else "",
        )
    console.print(table)
    ex = run.extraction
    if extract:
        console.print(
            f"Model read {ex.processed} item(s): {ex.proposals} proposal(s), "
            f"{ex.dropped} dropped for missing evidence."
        )
        if ex.error:
            console.print(f"[yellow]Stopped early: {ex.error}[/] (items wait for the next sync)")
    if run.google.reauth_needed:
        for email in run.google.reauth_needed:
            console.print(f"[red]{email} needs you to sign in again:[/] meow google login {email}")
        raise typer.Exit(1)
