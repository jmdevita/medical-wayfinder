"""Street View edge-walker routes (per-edge regenerate, accept, discard,
read sidecar, and on-demand pano proxy).

The bulk job (`POST /streetview-edges`) lives in `routes/llm_jobs.py` to sit
next to the other LLM-driven Job kickoffs. Everything else is here.

All routes are gated by `require_facility_editor`.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.auth import CurrentUser, require_facility_editor
from app.demo_mode import demo_block
from app.locks import locks
from app.rate_limits import limit_for
from app.services.locate import resolve_paths, suggestions_path_for
from app.services.streetview_edges import (
    accept_suggestion,
    load_suggestions,
    regenerate_one,
    remove_suggestion,
    scrub_secrets,
)

router = APIRouter(tags=["streetview-edges"])

_SLUG_PATTERN = re.compile(r"^[a-z0-9_]{2,64}$")
_NODE_ID_PATTERN = re.compile(r"^[a-z0-9_]{1,80}$")
_PANO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{10,32}$")


def _validate_slug(slug: str) -> None:
    if not _SLUG_PATTERN.match(slug):
        raise HTTPException(status_code=422, detail=f"Invalid slug '{slug}'.")
    facility_path, _topology_path, _source = resolve_paths(slug)
    if not facility_path.exists():
        raise HTTPException(status_code=404, detail=f"Facility '{slug}' not found")


def _validate_node_id(name: str, value: str) -> None:
    if not _NODE_ID_PATTERN.match(value):
        raise HTTPException(status_code=422, detail=f"Invalid {name}: {value!r}")


# --- GET sidecar ----------------------------------------------------------

@router.get("/streetview-edges/{slug}/suggestions")
async def get_suggestions(
    slug: str = Path(..., min_length=2, max_length=64, pattern=_SLUG_PATTERN.pattern),
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _validate_slug(slug)
    return load_suggestions(slug)


# --- POST per-edge regenerate --------------------------------------------

class RegenerateRequest(BaseModel):
    use_routing: bool = Field(default=True)


@router.post(
    "/streetview-edges/{slug}/edges/{from_id}/{to_id}/regenerate",
    dependencies=[Depends(demo_block)],
)
@limit_for("streetview_edges_regenerate")
async def regenerate_edge(
    request: Request,
    response: Response,
    slug: str,
    from_id: str,
    to_id: str,
    req: RegenerateRequest | None = None,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _ = request
    _ = response  # injected so slowapi can stamp rate-limit headers
    _validate_slug(slug)
    _validate_node_id("from_id", from_id)
    _validate_node_id("to_id", to_id)
    use_routing = req.use_routing if req is not None else True
    try:
        suggestion = await regenerate_one(
            slug=slug, from_id=from_id, to_id=to_id, use_routing=use_routing,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=scrub_secrets(str(exc))) from exc
    return suggestion


# --- POST accept ----------------------------------------------------------

class AcceptRequest(BaseModel):
    from_id: str = Field(..., min_length=1, max_length=80, pattern=_NODE_ID_PATTERN.pattern)
    to_id: str = Field(..., min_length=1, max_length=80, pattern=_NODE_ID_PATTERN.pattern)
    # Phase 3: for user_photos suggestions, controls whether the
    # photo-derived polyline replaces the existing edge geometry. Ignored for
    # streetview-source suggestions (they never write geometry).
    replace_geometry: bool = True


@router.post("/streetview-edges/{slug}/accept")
async def accept(
    slug: str,
    req: AcceptRequest,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _validate_slug(slug)
    # Same lock contract as PUT /facilities/{slug}/topology — accept mutates
    # topology.json and would race with a concurrent editor save otherwise.
    locks.assert_writable(slug, user.login, enforce=user.auth_enforced)
    try:
        result = accept_suggestion(
            slug, req.from_id, req.to_id,
            replace_geometry=req.replace_geometry,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"slug": slug, **result}


# --- DELETE discard -------------------------------------------------------

@router.delete("/streetview-edges/{slug}/suggestions/{from_id}/{to_id}")
async def discard(
    slug: str,
    from_id: str,
    to_id: str,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _validate_slug(slug)
    _validate_node_id("from_id", from_id)
    _validate_node_id("to_id", to_id)
    sidecar = remove_suggestion(slug, from_id, to_id)
    return {"slug": slug, "remaining": len(sidecar.get("suggestions", []))}


# --- GET pano proxy -------------------------------------------------------

# Google Street View ToS forbids long-term caching. We proxy each pano fetch
# fresh on demand so we never persist JPEG bytes, and require an editor on
# every call so quota cannot be exhausted by anonymous traffic.

@router.get(
    "/streetview-edges/{slug}/panos/{pano_id}.jpg",
    dependencies=[Depends(demo_block)],
)
@limit_for("streetview_edges_pano")
async def pano_proxy(
    request: Request,
    response: Response,
    slug: str,
    pano_id: str,
    heading: float = 0,
    fov: int = 90,
    pitch: int = 0,
    size: str = "640x640",
    user: CurrentUser = Depends(require_facility_editor),
) -> Response:
    _ = user
    _ = request
    _ = response  # injected so slowapi can stamp rate-limit headers
    _validate_slug(slug)
    if not _PANO_ID_PATTERN.match(pano_id):
        raise HTTPException(status_code=422, detail=f"Invalid pano_id {pano_id!r}.")
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="GOOGLE_MAPS_API_KEY is not set.")
    if not re.match(r"^\d{2,4}x\d{2,4}$", size) or any(
        int(d) > 640 for d in size.split("x")
    ):
        raise HTTPException(status_code=422, detail="size must be NxN with N<=640.")
    # Bound the rest of the params so a malicious editor can't pump huge
    # values into a Google URL or trigger Google to reject the request in a
    # way that leaks the URL in the response.
    if not (-180.0 <= heading <= 540.0):
        raise HTTPException(status_code=422, detail="heading out of range")
    if not (10 <= fov <= 120):
        raise HTTPException(status_code=422, detail="fov must be in [10,120]")
    if not (-90 <= pitch <= 90):
        raise HTTPException(status_code=422, detail="pitch must be in [-90,90]")

    params = {
        "size": size,
        "pano": pano_id,
        "heading": round(heading, 2),
        "fov": fov,
        "pitch": pitch,
        "key": api_key,
        "source": "outdoor",
    }
    async with httpx.AsyncClient(timeout=30.0) as http:
        try:
            r = await http.get(
                "https://maps.googleapis.com/maps/api/streetview", params=params,
            )
        except httpx.HTTPError as exc:
            # Scrub the API key out of any URL embedded in the exception text
            # before surfacing it to the editor.
            raise HTTPException(
                status_code=502,
                detail=scrub_secrets(f"Street View fetch failed: {exc}"),
            ) from exc
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Street View returned {r.status_code}.")
    # No long-term cache (ToS); allow short browser-side cache for the lightbox session.
    return Response(
        content=r.content,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )
