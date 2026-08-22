"""Main FastAPI application factory for Meow OS."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from api.routes import (
    dashboard, tasks, calendar, chat, projects, 
    opportunities, memory, goals, briefings, actions
)
from api.middleware.audit import AuditMiddleware
from api.middleware.auth import LocalAuthMiddleware

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup/shutdown."""
    logger.info("Initializing DB...")
    # TODO(Phase 2): Initialize SQLite DB here
    logger.info("Starting scheduler...")
    # TODO(Phase 2): Start APScheduler here
    logger.info("Loading agents and models...")
    # TODO(Phase 2): Load Ollama/ChromaDB here
    yield
    logger.info("Shutting down Meow OS API...")

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Meow OS",
        description="Local-first, multi-agent Personal AI Operating System.",
        version="1.0.0",
        lifespan=lifespan
    )

    # Middleware (Order matters: outermost first)
    app.add_middleware(LocalAuthMiddleware)
    app.add_middleware(AuditMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(calendar.router, prefix="/api/calendar", tags=["calendar"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(chat.router, prefix="/ws/chat", tags=["chat_ws"])
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(opportunities.router, prefix="/api/opportunities", tags=["opportunities"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(goals.router, prefix="/api/goals", tags=["goals"])
    app.include_router(briefings.router, prefix="/api/briefings", tags=["briefings"])
    app.include_router(actions.router, prefix="/api/actions", tags=["actions"])

    # Health check
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "version": app.version}

    # Static files for UI
    import os
    ui_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui")
    os.makedirs(ui_dir, exist_ok=True)
    
    app.mount("/static", StaticFiles(directory=ui_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def serve_index():
        index_path = os.path.join(ui_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                return f.read()
        return "<h1>Meow OS UI not found</h1>"

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
