# Wayfinder Atlas

A dashboard for authoring and maintaining hospital topology data — the data
that powers the on-device wayfinding model in the Medical Wayfinder Flutter app.

This is the V2 of the standalone `tools/topology_editor.html` page: same job,
better workflow, multiple facilities, hosted-ready.

## Layout

```
atlas/
  frontend/    Vite + React + TypeScript + Tailwind dashboard
  backend/     FastAPI service that wraps the existing tools/ Python scripts
```

The backend imports from the repo's existing `tools/` directory — no logic
duplication. OSM bootstrap, LLM extraction, edge drafting, alias expansion,
and validation all keep their existing entry points.

## Stack

**Frontend** — Vite, React 18, TypeScript, TanStack Router, TanStack Query,
Zustand, Tailwind v4, react-leaflet, lucide-react.

**Backend** — FastAPI, Pydantic v2, httpx, Server-Sent Events for long-running
jobs (OSM bootstrap, LLM calls).

**Storage** — filesystem only for v1. Source of truth is:

- `tools/bootstrap/<slug>/` for in-progress drafts
- `health_wayfinder/assets/facilities/<slug>.json` (+ `.topology.json`) for
  published facilities

Git provides versioning. A real registry server is deferred to v3.

## Quickstart

```bash
# from atlas/
make install        # one-time: npm install + pip install
make dev            # runs frontend (5173) and backend (8000) concurrently
```

Open http://localhost:5173. The Vite dev server proxies `/api` to FastAPI on
:8000, so the frontend stays origin-clean.

## Why this exists

Authoring a new hospital has three legs: bootstrap building/parking/transit
nodes from OpenStreetMap, hand-author the landmark prose and walking edges
that make routes patient-readable, and register the facility for the app to
pick up at startup. This dashboard is the authoring surface that makes the
second leg humane.
