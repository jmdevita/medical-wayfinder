"""
POST /bootstrap — kick off an OSM bootstrap as a background job.

Wraps the existing tools/fetch_osm_for_facility.py pipeline. Returns a job_id
the caller can use to subscribe to /jobs/{job_id}/stream.
"""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth import CurrentUser, require_facility_editor
from app.demo_mode import demo_block
from app.jobs import jobs
from app.rate_limits import limit_for
from app.paths import BOOTSTRAP_DIR, FACILITIES_DIR
from app.services.osm_bootstrap import run_bootstrap, slugify

router = APIRouter(tags=["bootstrap"])

_VALID_SLUG = re.compile(r"^[a-z0-9_]{2,64}$")


class BootstrapRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=200, description="Hospital name or address")
    slug: str | None = Field(
        default=None,
        description="Override the auto-generated slug. Lowercase letters, digits, underscores.",
    )
    include_landmarks: bool = Field(
        default=False,
        description="Also seed landmark nodes for cafes, shops, etc. Useful for small urban clinics.",
    )


class BootstrapResponse(BaseModel):
    job_id: str
    slug: str
    stream_url: str


@router.post(
    "/bootstrap",
    response_model=BootstrapResponse,
    status_code=202,
    dependencies=[Depends(demo_block)],
)
@limit_for("bootstrap")
async def kick_off_bootstrap(
    request: Request,
    response: Response,
    req: BootstrapRequest,
    user: CurrentUser = Depends(require_facility_editor),
) -> BootstrapResponse:
    _ = user
    _ = request
    _ = response  # injected by FastAPI so slowapi can stamp rate-limit headers
    slug = req.slug or slugify(req.query)
    if not _VALID_SLUG.match(slug):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid slug '{slug}'. Use lowercase letters, digits, underscores (2-64 chars).",
        )

    # Refuse to clobber an existing facility — caller can delete first if they
    # want to redo. This keeps `make a new facility` distinct from `re-run OSM`.
    if (FACILITIES_DIR / f"{slug}.json").exists() or (BOOTSTRAP_DIR / slug).exists():
        raise HTTPException(
            status_code=409,
            detail=f"Facility '{slug}' already exists. Pick a different slug or delete the existing one.",
        )

    job = jobs.create(kind="osm_bootstrap")
    asyncio.create_task(
        run_bootstrap(job, slug=slug, query=req.query, include_landmarks=req.include_landmarks)
    )
    return BootstrapResponse(job_id=job.id, slug=slug, stream_url=f"/jobs/{job.id}/stream")
