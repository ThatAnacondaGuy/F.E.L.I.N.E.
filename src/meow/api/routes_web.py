"""Server-rendered UI. Plain HTML forms, no JavaScript required."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from meow.api.deps import COOKIE_NAME, DB, LLM, Now, ProfileDep, nudge_worker, require_auth
from meow.config import Profile
from meow.db.models import FocusSession
from meow.domain.timeutil import format_duration
from meow.llm.extraction import ExtractionError, Extractor
from meow.security import session_value, verify_login_code
from meow.services import (
    accounts,
    audit,
    autonomy,
    briefings,
    capture,
    planning,
    proposals,
    syncing,
    tasks,
)
from meow.types import (
    BlockKind,
    BriefingKind,
    Category,
    Importance,
    ProposalKind,
    ProposalStatus,
    TaskStatus,
)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
public = APIRouter(include_in_schema=False)
router = APIRouter(include_in_schema=False, dependencies=[Depends(require_auth)])

NOTES = {
    "approved": "Approved.",
    "rejected": "Rejected. Meow will learn from that.",
    "task_added": "Task added.",
    "task_done": "Nice. Marked done.",
    "promoted": "Promoted. Meow will act on its own for this from now on.",
    "nothing": "Nothing new to propose.",
    "proposed": "New focus blocks are waiting in your inbox.",
    "duplicate": "You already captured that; showing the earlier proposals.",
}


def _render(request: Request, name: str, profile: Profile, **ctx: Any) -> HTMLResponse:
    tz = profile.user.tz

    def local(value: datetime | str | None, fmt: str = "%a %d %b, %H:%M") -> str:
        if not value:
            return ""
        moment = datetime.fromisoformat(value) if isinstance(value, str) else value
        return moment.astimezone(tz).strftime(fmt)

    note = NOTES.get(request.query_params.get("note", ""), "")
    if request.query_params.get("note") == "synced":
        new, made = request.query_params.get("n", "0"), request.query_params.get("p", "0")
        note = f"Synced: {new} new item(s), {made} new proposal(s)."
    if request.query_params.get("note") == "captured":
        made, dropped = request.query_params.get("n", "0"), request.query_params.get("d", "0")
        note = f"Filed {made} proposal(s) for review" + (
            f"; dropped {dropped} the source didn't back up." if dropped != "0" else "."
        )
    return templates.TemplateResponse(
        request,
        name,
        {
            "profile": profile,
            "local": local,
            "duration": format_duration,
            "note": note,
            "error": request.query_params.get("error", ""),
            "pending_count": ctx.pop("pending_count", None),
            **ctx,
        },
    )


def _back(path: str, **params: str | int) -> RedirectResponse:
    query = urlencode(params)
    return RedirectResponse(f"{path}?{query}" if query else path, status_code=303)


def _parse_local(value: str, profile: Profile) -> datetime | None:
    if not value.strip():
        return None
    return datetime.fromisoformat(value).replace(tzinfo=profile.user.tz)


# ── login ────────────────────────────────────────────────────────────────


@public.get("/login")
def login(request: Request, code: str = "", ts: int = 0) -> Response:
    token: str = request.app.state.token
    if not verify_login_code(token, code, ts, now=time.time()):
        return HTMLResponse(
            templates.get_template("locked.html").render(expired=bool(code)), status_code=401
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        session_value(token),
        httponly=True,
        samesite="strict",
        max_age=60 * 60 * 24 * 30,
    )
    return response


# ── pages ────────────────────────────────────────────────────────────────


def _pending(db: DB) -> int:
    return len(proposals.list_proposals(db, ProposalStatus.PENDING))


@router.get("/", response_class=HTMLResponse)
def today(request: Request, db: DB, profile: ProfileDep, now: Now) -> HTMLResponse:
    proposals.expire_stale(db, now)
    schedule = tasks.schedule_for(profile)
    tz = profile.user.tz
    block = schedule.block_at(now)
    plan = tasks.build_plan(db, profile, now)
    # "Today" is the awake day: it ends when the next sleep block starts.
    day_end = schedule.next_start(BlockKind.SLEEP, now) or now + timedelta(hours=24)
    booked = list(
        db.scalars(
            select(FocusSession)
            .where(FocusSession.end_at > now, FocusSession.start_at < day_end)
            .order_by(FocusSession.start_at)
        )
    )
    suggested = [s for s in plan.sessions if s.interval.start < day_end]
    hour = now.astimezone(tz).hour
    greeting = (
        "Good morning"
        if 5 <= hour < 12
        else "Good afternoon"
        if hour < 17
        else "Good evening"
        if hour < 22
        else "Burning the midnight oil"
    )
    return _render(
        request,
        "today.html",
        profile,
        greeting=greeting,
        now=now,
        block=block,
        booked=booked,
        suggested=suggested,
        at_risk=plan.at_risk,
        ranked=tasks.ranked_tasks(db, profile, now)[:6],
        pending_count=_pending(db),
        quiet=schedule.is_quiet(now),
        briefing=briefings.latest(db, profile, now),
        brief_kind="morning" if now.astimezone(tz).hour < 14 else "evening",
        **_sync_summary(db),
    )


@router.post("/briefings/{kind}")
def make_briefing(
    request: Request, kind: BriefingKind, db: DB, profile: ProfileDep, now: Now
) -> Response:
    briefings.generate(db, profile, kind, now, request.app.state.notifier, force=True)
    return _back("/")


def _sync_summary(db: DB) -> dict[str, Any]:
    connected = accounts.list_accounts(db, enabled_only=True)
    successes = [st.last_success_at for st in accounts.sync_states(db) if st.last_success_at]
    return {
        "connected": connected,
        "reauth": [a for a in connected if a.needs_reauth],
        "sync_errors": [st for st in accounts.sync_states(db) if st.last_error],
        "last_sync": max(successes) if successes else None,
    }


@router.post("/sync")
def sync_now(request: Request, db: DB, now: Now, llm: LLM) -> Response:
    deps = request.app.state.sync_deps
    try:
        run = syncing.run_sync(
            db,
            request.app.state.settings,
            now,
            llm=llm,
            apis=deps.apis,
            store=deps.store,
            load=deps.load,
        )
    except syncing.SyncBusy:
        return _back("/", error="A sync is already running; try again in a minute.")
    return _back(
        "/inbox" if run.google.proposals + run.extraction.proposals else "/",
        note="synced",
        n=run.google.new_items,
        p=run.google.proposals + run.extraction.proposals,
    )


@router.get("/inbox", response_class=HTMLResponse)
def inbox(request: Request, db: DB, profile: ProfileDep, now: Now) -> HTMLResponse:
    proposals.expire_stale(db, now)
    pending = proposals.inbox_order(proposals.list_proposals(db, ProposalStatus.PENDING))
    return _render(
        request,
        "inbox.html",
        profile,
        proposals=pending,
        pending_count=len(pending),
        focus_count=sum(p.kind is ProposalKind.SCHEDULE_FOCUS_BLOCK for p in pending),
        importance=list(Importance),
    )


@router.post("/inbox/approve-focus-blocks")
def approve_focus_blocks(request: Request, db: DB, profile: ProfileDep, now: Now) -> Response:
    try:
        proposals.approve_all(db, profile, ProposalKind.SCHEDULE_FOCUS_BLOCK, now=now)
    except (proposals.ProposalError, tasks.TaskNotFound) as exc:
        return _back("/inbox", error=str(exc)[:200])
    nudge_worker(request)  # put them on the Meow calendar now, not in 30 minutes
    return _back("/inbox", note="approved")


@router.post("/inbox/{proposal_id}/approve")
def approve(
    request: Request,
    proposal_id: str,
    db: DB,
    profile: ProfileDep,
    title: Annotated[str | None, Form()] = None,
    due: Annotated[str | None, Form()] = None,
    minutes: Annotated[str | None, Form()] = None,
    importance: Annotated[Importance | None, Form()] = None,
) -> Response:
    edits: dict[str, Any] = {}
    if title is not None:
        edits["title"] = title
    if due is not None:
        parsed = _parse_local(due, profile)
        edits["due_at"] = parsed.isoformat() if parsed else None
    if minutes is not None:
        edits["estimated_minutes"] = int(minutes) if minutes.strip() else None
    if importance is not None:
        edits["importance"] = importance.value
    try:
        approved = proposals.approve(db, profile, proposal_id, edits=edits or None)
    except (proposals.ProposalError, proposals.ProposalNotFound, tasks.TaskNotFound) as exc:
        return _back("/inbox", error=str(exc)[:200])
    if approved.kind is ProposalKind.SCHEDULE_FOCUS_BLOCK:
        nudge_worker(request)
    return _back("/inbox", note="approved")


@router.post("/inbox/{proposal_id}/reject")
def reject(
    proposal_id: str, db: DB, profile: ProfileDep, reason: Annotated[str, Form()] = ""
) -> Response:
    try:
        proposals.reject(db, profile, proposal_id, reason=reason)
    except (proposals.ProposalError, proposals.ProposalNotFound) as exc:
        return _back("/inbox", error=str(exc)[:200])
    return _back("/inbox", note="rejected")


@router.post("/capture")
def capture_text(
    db: DB,
    profile: ProfileDep,
    now: Now,
    llm: LLM,
    text: Annotated[str, Form()],
    title: Annotated[str, Form()] = "",
) -> Response:
    try:
        result = capture.capture_text(
            db, profile, Extractor(llm, profile), text, title=title, now=now
        )
    except (ExtractionError, ValueError) as exc:
        return _back("/inbox", error=f"Couldn't extract tasks: {exc}"[:300])
    if result.duplicate:
        return _back("/inbox", note="duplicate")
    return _back("/inbox", note="captured", n=len(result.proposals), d=len(result.dropped))


@router.post("/plan/propose")
def propose_plan(db: DB, profile: ProfileDep, now: Now) -> Response:
    _, created = planning.propose_focus_blocks(db, profile, now)
    return _back("/inbox" if created else "/", note="proposed" if created else "nothing")


@router.get("/tasks", response_class=HTMLResponse)
def task_list(request: Request, db: DB, profile: ProfileDep, now: Now) -> HTMLResponse:
    return _render(
        request,
        "tasks.html",
        profile,
        ranked=tasks.ranked_tasks(db, profile, now),
        importance=list(Importance),
        categories=list(Category),
        pending_count=_pending(db),
    )


@router.post("/tasks")
def add_task(
    db: DB,
    profile: ProfileDep,
    title: Annotated[str, Form()],
    due: Annotated[str, Form()] = "",
    minutes: Annotated[str, Form()] = "",
    importance: Annotated[Importance, Form()] = Importance.MEDIUM,
    category: Annotated[Category, Form()] = Category.PERSONAL,
    course_code: Annotated[str, Form()] = "",
    career_relevance: Annotated[float, Form()] = 0.0,
) -> Response:
    try:
        draft = tasks.TaskDraft(
            title=title,
            due_at=_parse_local(due, profile),
            estimated_minutes=int(minutes) if minutes.strip() else None,
            importance=importance,
            category=category,
            course_code=course_code or None,
            career_relevance=career_relevance,
        )
    except ValueError as exc:
        return _back("/tasks", error=str(exc).splitlines()[0][:200])
    tasks.add_task(db, draft)
    return _back("/tasks", note="task_added")


@router.post("/tasks/{task_id}/done")
def task_done(request: Request, task_id: str, db: DB, now: Now) -> Response:
    try:
        tasks.set_status(db, task_id, TaskStatus.DONE, actor="user", now=now)
    except tasks.TaskNotFound:
        raise HTTPException(404, "Task not found") from None
    nudge_worker(request)  # take its focus blocks off the calendar soon
    return _back("/tasks", note="task_done")


@router.get("/autonomy", response_class=HTMLResponse)
def autonomy_page(request: Request, db: DB, profile: ProfileDep) -> HTMLResponse:
    statuses = [autonomy.status(db, profile, k) for k in ProposalKind]
    return _render(request, "autonomy.html", profile, statuses=statuses, pending_count=_pending(db))


@router.post("/autonomy/{kind}/promote")
def promote(kind: ProposalKind, db: DB, profile: ProfileDep) -> Response:
    try:
        autonomy.promote(db, profile, kind)
    except autonomy.PromotionRefused as exc:
        return _back("/autonomy", error=str(exc)[:300])
    return _back("/autonomy", note="promoted")


@router.get("/activity", response_class=HTMLResponse)
def activity(request: Request, db: DB, profile: ProfileDep) -> HTMLResponse:
    return _render(
        request, "activity.html", profile, entries=audit.recent(db, 200), pending_count=_pending(db)
    )
