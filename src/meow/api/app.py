"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from meow import __version__
from meow.api import routes_api, routes_web
from meow.config import Settings
from meow.db.engine import make_engine, make_session_factory, upgrade
from meow.domain.timeutil import utcnow
from meow.integrations.google.auth import TokenStore, load_credentials
from meow.integrations.google.sync import APIs, CredentialLoader
from meow.llm.ollama import JSONChat, OllamaClient
from meow.notify import MacNotifier, Notifier
from meow.security import load_or_create_token
from meow.services.background import BriefingJob, Job, SyncJob, Worker


@dataclass(frozen=True, slots=True)
class SyncDeps:
    """Google access for manual syncs. Tests swap in fakes; None means the real thing."""

    apis: APIs | None = None
    store: TokenStore | None = None
    load: CredentialLoader = load_credentials


LOCAL_HOSTS = ["127.0.0.1", "localhost"]


def create_app(
    settings: Settings | None = None,
    *,
    clock: Callable[[], datetime] = utcnow,
    llm_factory: Callable[[], JSONChat] | None = None,
    sync_deps: SyncDeps | None = None,
    notifier: Notifier | None = None,
    background: bool = True,
) -> FastAPI:
    settings = settings or Settings()
    profile = settings.profile  # validate config before anything starts
    port = profile.server.port

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_home()
        engine = make_engine(settings.db_path)
        upgrade(engine)
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        app.state.token = load_or_create_token(settings)
        worker = None
        if background:
            jobs: list[Job] = [
                SyncJob(settings, app.state.llm_factory),
                BriefingJob(settings, app.state.notifier),
            ]
            worker = Worker(app.state.session_factory, jobs, clock)
            worker.start()
        app.state.worker = worker
        yield
        if worker:
            worker.stop()
        engine.dispose()

    app = FastAPI(
        title="Meow OS",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.clock = clock
    app.state.llm_factory = llm_factory or (
        lambda: OllamaClient(profile.llm.base_url, **profile.llm.client_options())
    )
    app.state.allowed_origins = {f"http://{host}:{port}" for host in LOCAL_HOSTS}
    app.state.sync_deps = sync_deps or SyncDeps()
    app.state.notifier = notifier or MacNotifier()
    app.state.worker = None

    # Rejects requests whose Host header isn't local: this is what defeats DNS rebinding.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[..., object]) -> Response:
        response: Response = await call_next(request)  # type: ignore[misc]
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; img-src 'self' data:; form-action 'self'; "
            "frame-ancestors 'none'",
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def html_errors(request: Request, exc: StarletteHTTPException) -> Response:
        if not request.url.path.startswith("/api") and exc.status_code in (401, 403):
            html = routes_web.templates.get_template("locked.html").render(
                expired=False, forbidden=exc.status_code == 403
            )
            return HTMLResponse(html, status_code=exc.status_code)
        return await http_exception_handler(request, exc)

    app.include_router(routes_api.public)
    app.include_router(routes_api.router)
    app.include_router(routes_web.public)
    app.include_router(routes_web.router)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    return app


def create_app_from_env() -> FastAPI:
    """Entry point for ``uvicorn --factory``."""
    return create_app()
