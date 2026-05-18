# syntax=docker/dockerfile:1.6
# Multi-stage build for the Wayfinder Atlas dashboard.
#
# Stage 1 — frontend build with Node 20.
# Stage 2 — Python 3.11-slim runtime that bundles tools/, atlas/backend, and
#           the built frontend, served by uvicorn on port 8000.
#
# Build context expects the repo root so we can COPY both atlas/ and tools/.

# ----- Stage 1 ---------------------------------------------------------------
FROM node:20-slim AS frontend-build
WORKDIR /build
COPY atlas/frontend/package.json atlas/frontend/package-lock.json ./
# Reproducible install — fails fast if package.json drifts from the lockfile.
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY atlas/frontend/ ./
RUN npm run build

# ----- Stage 2 ---------------------------------------------------------------
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ATLAS_FACILITIES_DIR=/data/facilities \
    ATLAS_BOOTSTRAP_DIR=/data/bootstrap \
    ATLAS_SERVE_STATIC=/app/frontend-dist \
    ATLAS_CORS_ORIGINS=

WORKDIR /app

# Tools the backend imports — OSM bootstrap, LLM extraction, etc.
COPY tools/ ./tools/

# Backend code + pyproject. We mirror the source layout (`atlas/backend`
# rather than `backend`) because `app/paths.py` derives REPO_ROOT by walking
# `parents[2].parent` from __file__ — that traversal needs an `atlas/` dir
# above `backend/` to land at /app instead of /, otherwise REPO_ROOT/tools
# resolves to /tools and `ensure_tools_on_path()` blows up.
COPY atlas/backend/ ./atlas/backend/
RUN pip install --upgrade pip && pip install -e ./atlas/backend

# Built frontend bundle.
COPY --from=frontend-build /build/dist /app/frontend-dist

# Demo-mode entrypoint scripts. Default CMD ignores them; demo deployments
# override entrypoint to /app/atlas-scripts/demo-entrypoint.sh (see
# atlas/docker-compose.demo.yml).
COPY atlas/scripts/ /app/atlas-scripts/
RUN chmod +x /app/atlas-scripts/*.sh

# Seed data shipped with the image. Mount /data for persistence in production.
#
# Three sources, three destinations:
#   facilities    <- health_wayfinder/assets/facilities/  (atlas/data/facilities
#                    is a symlink to this; Docker BuildKit's COPY does not
#                    reliably follow symlinks, so reach through directly)
#   bootstrap     <- empty dir  (BOOTSTRAP_DIR exists, no scratch data shipped)
#   roles.yaml    <- atlas/data/roles.yaml
#
# /data/proposals is created lazily by assert_repo_layout() on first contributor
# fork, so no need to pre-create it here.

RUN mkdir -p /data-seed/facilities /data-seed/bootstrap
COPY health_wayfinder/assets/facilities/ /data-seed/facilities/
COPY atlas/data/roles.yaml /data-seed/roles.yaml

RUN mkdir -p /data && cp -r /data-seed/. /data/ || true

EXPOSE 8000

# Single worker is fine when the job runner is in-memory. With ATLAS_REDIS_URL
# set (see docker-compose.yml) you can bump --workers safely; the Redis-backed
# JobStore handles cross-worker job state and SSE replay.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/atlas/backend"]
