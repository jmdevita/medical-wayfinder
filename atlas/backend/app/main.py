"""
Atlas backend entry point.

Run from atlas/backend/ via:

    uvicorn app.main:app --reload --port 8000

All API routes are mounted under /api so a single container can serve both
the API and the built frontend (the latter at /). The Vite dev proxy targets
/api directly without rewriting, so dev and prod take the same path.

Set ATLAS_SERVE_STATIC=/path/to/dist to also serve the built frontend.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import SETTINGS as AUTH_SETTINGS, install_session_middleware
from app.jobs import jobs
from app.logging_config import configure_logging
from app.middleware.request_id import RequestIdMiddleware
from app.paths import assert_repo_layout
from app.rate_limits import install_rate_limit_handler
from app.routes import auth as auth_routes, bootstrap, facilities, health, jobs as jobs_routes, llm_jobs, locks as locks_routes, photo_edges as photo_edges_routes, proposals as proposals_routes, publish, settings as settings_routes, streetview_edges as streetview_edges_routes


def _cors_origins() -> list[str]:
    """
    Read allowed CORS origins from ATLAS_CORS_ORIGINS (comma-separated).
    Defaults to the local Vite dev server. Set explicitly when deploying.
    """
    raw = os.environ.get(
        "ATLAS_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    AUTH_SETTINGS.assert_runnable()
    assert_repo_layout()
    # If we're using Redis, fail fast on a misconfigured connection so the
    # orchestrator's readiness probe stays red instead of half-serving.
    ping = getattr(jobs, "ping", None)
    if callable(ping):
        await ping()
    try:
        yield
    finally:
        aclose = getattr(jobs, "aclose", None)
        if callable(aclose):
            await aclose()


app = FastAPI(
    title="Wayfinder Atlas API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Session must be installed BEFORE routes so request.session exists.
install_session_middleware(app)
# Request-ID runs as the outermost layer so every log line gets it.
app.add_middleware(RequestIdMiddleware)

install_rate_limit_handler(app)

api = APIRouter(prefix="/api")
api.include_router(health.router)
api.include_router(auth_routes.router)
api.include_router(facilities.router)
api.include_router(locks_routes.router)
api.include_router(jobs_routes.router)
api.include_router(bootstrap.router)
api.include_router(llm_jobs.router)
api.include_router(streetview_edges_routes.router)
api.include_router(photo_edges_routes.router)
api.include_router(publish.router)
api.include_router(proposals_routes.router)
api.include_router(settings_routes.router)
app.include_router(api)


@app.get("/api")
def api_index() -> dict[str, str]:
    return {
        "name": "Wayfinder Atlas API",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


# Optional: serve the built frontend bundle when running in single-container
# mode. ATLAS_SERVE_STATIC should point to the absolute path of frontend/dist.
_static_dir = os.environ.get("ATLAS_SERVE_STATIC")
if _static_dir and Path(_static_dir).exists():
    static_path = Path(_static_dir)

    # Static assets first (the bundler hashes them, so the path is precise).
    app.mount("/assets", StaticFiles(directory=static_path / "assets"), name="assets")

    @app.get("/")
    @app.get("/{path:path}")
    def spa_index(path: str = ""):
        # Real 404 for any /api/* that didn't match a registered route, so
        # callers don't get the SPA's index.html when they meant the API.
        if path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not Found")
        # Everything else is the SPA — let it route client-side.
        return FileResponse(static_path / "index.html")
