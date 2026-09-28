"""JSON API, used by the CLI-less clients (desktop cat, scripts). Bearer-token authenticated."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from meow import __version__
from meow.api import schemas as s
from meow.api.deps import DB, LLM, Now, ProfileDep, require_auth
from meow.domain.prioritizer import Prioritizer
from meow.llm.extraction import ExtractionError, Extractor
from meow.services import accounts, audit, autonomy, capture, planning, proposals, syncing, tasks
from meow.types import ProposalKind, ProposalStatus, TaskStatus

public = APIRouter(prefix="/api")
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


@public.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/tasks")
def list_tasks(db: DB, profile: ProfileDep, now: Now) -> list[s.TaskOut]:
    return [s.TaskOut.of(r.task, r.score) for r in tasks.ranked_tasks(db, profile, now)]


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(draft: tasks.TaskDraft, db: DB, profile: ProfileDep, now: Now) -> s.TaskOut:
    task = tasks.add_task(db, draft)
    score = Prioritizer(profile.scoring, profile.courses).score(tasks.facts(task), now)
    return s.TaskOut.of(task, score)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: DB, profile: ProfileDep, now: Now) -> s.TaskOut:
    try:
        task = tasks.get_task(db, task_id)
    except tasks.TaskNotFound:
        raise HTTPException(404, "Task not found") from None
    score = Prioritizer(profile.scoring, profile.courses).score(tasks.facts(task), now)
    return s.TaskOut.of(task, score)


@router.post("/tasks/{task_id}/{new_status}")
def set_task_status(task_id: str, new_status: TaskStatus, db: DB) -> s.TaskOut:
    try:
        return s.TaskOut.of(tasks.set_status(db, task_id, new_status, actor="user"))
    except tasks.TaskNotFound:
        raise HTTPException(404, "Task not found") from None


@router.get("/proposals")
def list_proposals(
    db: DB,
    status_: Annotated[ProposalStatus | None, Query(alias="status")] = ProposalStatus.PENDING,
) -> list[s.ProposalOut]:
    return [s.ProposalOut.of(p) for p in proposals.list_proposals(db, status_)]


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: str, body: s.ApproveIn, db: DB, profile: ProfileDep) -> s.ProposalOut:
    try:
        return s.ProposalOut.of(proposals.approve(db, profile, proposal_id, edits=body.edits))
    except proposals.ProposalNotFound:
        raise HTTPException(404, "Proposal not found") from None
    except (proposals.ProposalError, tasks.TaskNotFound) as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: str, body: s.RejectIn, db: DB, profile: ProfileDep) -> s.ProposalOut:
    try:
        return s.ProposalOut.of(proposals.reject(db, profile, proposal_id, reason=body.reason))
    except proposals.ProposalNotFound:
        raise HTTPException(404, "Proposal not found") from None
    except proposals.ProposalError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/capture")
def capture_text(
    body: s.CaptureIn, db: DB, profile: ProfileDep, now: Now, llm: LLM
) -> s.CaptureOut:
    try:
        result = capture.capture_text(
            db, profile, Extractor(llm, profile), body.text, title=body.title, now=now
        )
    except ExtractionError as exc:
        raise HTTPException(502, f"Extraction failed: {exc}") from None
    return s.CaptureOut(
        source_id=result.source.id,
        duplicate=result.duplicate,
        proposals=[s.ProposalOut.of(p) for p in result.proposals],
        dropped=[{"title": t, "reason": r} for t, r in result.dropped],
    )


@router.get("/plan")
def get_plan(db: DB, profile: ProfileDep, now: Now) -> s.PlanOut:
    return s.PlanOut.of(tasks.build_plan(db, profile, now))


@router.post("/plan/propose")
def propose_plan(db: DB, profile: ProfileDep, now: Now) -> list[s.ProposalOut]:
    _, created = planning.propose_focus_blocks(db, profile, now)
    return [s.ProposalOut.of(p) for p in created]


@router.get("/autonomy")
def autonomy_status(db: DB, profile: ProfileDep) -> list[s.AutonomyOut]:
    return [s.AutonomyOut.of(autonomy.status(db, profile, k)) for k in ProposalKind]


@router.post("/autonomy/{kind}/promote")
def promote(kind: ProposalKind, db: DB, profile: ProfileDep) -> s.AutonomyOut:
    try:
        autonomy.promote(db, profile, kind)
    except autonomy.PromotionRefused as exc:
        raise HTTPException(409, str(exc)) from None
    return s.AutonomyOut.of(autonomy.status(db, profile, kind))


@router.get("/audit")
def audit_log(db: DB, limit: Annotated[int, Query(ge=1, le=1000)] = 100) -> list[s.AuditOut]:
    return [s.AuditOut.of(e) for e in audit.recent(db, limit)]


@router.get("/sync")
def sync_status(db: DB) -> list[s.AccountOut]:
    out = []
    for acct in accounts.list_accounts(db):
        states = [
            s.SyncStateOut(
                source=st.source,
                last_success_at=st.last_success_at,
                last_attempt_at=st.last_attempt_at,
                last_error=st.last_error,
                items_new=st.items_new,
            )
            for st in accounts.sync_states(db, acct.email)
        ]
        out.append(
            s.AccountOut(
                email=acct.email,
                sources=acct.sources,
                enabled=acct.enabled,
                needs_reauth=acct.needs_reauth,
                last_error=acct.last_error,
                authorized_at=acct.authorized_at,
                sync=states,
            )
        )
    return out


@router.post("/sync")
def sync_now(request: Request, db: DB, now: Now, llm: LLM) -> s.SyncRunOut:
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
    except syncing.SyncBusy as exc:
        raise HTTPException(409, str(exc)) from None
    return s.SyncRunOut.of(run)
