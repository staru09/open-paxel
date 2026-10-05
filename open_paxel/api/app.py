from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from open_paxel.api.routes import profile, sessions, uploads
from open_paxel.config import Settings
from open_paxel.db.repository import SQLiteRepository
from open_paxel.logging_config import setup_logging
from open_paxel.reset import cleanup_incoming

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _clear_ephemeral_state(settings: Settings, repo: SQLiteRepository) -> None:
    deleted = repo.clear_ephemeral_state()
    incoming = settings.home / "incoming"
    cleanup_incoming(incoming)
    logger.info(
        "Cleared ephemeral state: %d job(s) removed, incoming dir reset",
        deleted,
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    repo: SQLiteRepository = app.state.repository
    app.state.instance_id = str(uuid.uuid4())

    if settings.ephemeral_jobs:
        _clear_ephemeral_state(settings, repo)

    yield

    if settings.ephemeral_jobs:
        _clear_ephemeral_state(settings, repo)
        logger.info("Server shutdown — ephemeral job state cleared")


def _install_spa(app: FastAPI) -> None:
    """Serve built frontend with index.html fallback for client-side routes."""
    if not STATIC_DIR.exists() or not (STATIC_DIR / "index.html").exists():
        return

    index_path = STATIC_DIR / "index.html"
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/")
    def spa_index():
        return FileResponse(index_path)

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api") or full_path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_path)


def create_app(settings: Settings | None = None) -> FastAPI:
    setup_logging()
    settings = settings or Settings.load()
    settings.home.mkdir(parents=True, exist_ok=True)
    repo = SQLiteRepository(settings.db_path)

    app = FastAPI(title="Open-Paxel", docs_url="/api/docs", lifespan=_lifespan)
    app.state.settings = settings
    app.state.repository = repo

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health(request: Request):
        return {"status": "ok", "instance_id": request.app.state.instance_id}

    app.include_router(profile.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(uploads.router, prefix="/api")

    _install_spa(app)

    return app
