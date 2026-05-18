# Atlas backend

FastAPI service that powers the Wayfinder Atlas dashboard.

## Why FastAPI

The repo's existing OSM bootstrap, LLM extraction, edge drafting, alias
expansion, and validation logic are all Python (`tools/`). FastAPI lets us
expose each as an HTTP endpoint without rewriting any of that work in
JavaScript. As the backend grows, those scripts get imported as modules
rather than shelled out.

## Endpoints (initial)

| Path | Status | Notes |
|---|---|---|
| `GET /health` | shipped | liveness |
| `GET /facilities` | shipped | scans `health_wayfinder/assets/facilities/` and `tools/bootstrap/` |
| `GET /facilities/{slug}` | shipped | returns facility + topology JSON |

Planned (in priority order):

- `POST /bootstrap` — wraps `tools/fetch_osm_for_facility.py`, streams progress over SSE
- `POST /extract-departments` — wraps `tools/fetch_departments_for_facility.py`
- `POST /draft-edges` — wraps `tools/draft_edges_for_facility.py`
- `POST /expand-aliases` — wraps `tools/fetch_aliases_for_facility.py`
- `PUT /facilities/{slug}/topology` — write topology JSON, run validator before persist
- `GET /validate/{slug}` — wraps `tools/validate_facility.py`
- `POST /facilities/{slug}/publish` — promote bootstrap to assets, optionally open a GitHub PR

## Run

The backend reuses the repo-root `env/` virtualenv (the one used by `tools/`
and `training/`). This is intentional: the backend imports from `tools/`, so a
single shared venv keeps the dependency graph honest.

```bash
# from atlas/  (one level above this directory)
make install-backend     # installs FastAPI + deps into ../env
make dev-backend         # uvicorn on :8000
```

OpenAPI docs: <http://localhost:8000/docs>.

OpenAPI docs: <http://localhost:8000/docs>.

## Storage

No database. Source of truth is the filesystem:

- `health_wayfinder/assets/facilities/<slug>.json` (+ `.topology.json`) — published
- `tools/bootstrap/<slug>/{facility,topology}.json` — drafts in progress

Git provides versioning. A registry server is deferred until v3.
