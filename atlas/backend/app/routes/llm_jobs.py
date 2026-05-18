"""
Long-running background jobs that touch facility data:
  - extract-departments  (LLM, 60-90s)
  - draft-edges          (footway routing, near-instant)
  - expand-aliases       (LLM, 20-40s)

Each kicks off a Job and returns its id + stream URL. Frontend tails progress
through /jobs/{id}/stream.
"""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, HttpUrl

from app.auth import CurrentUser, require_facility_editor
from app.demo_mode import demo_block
from app.jobs import jobs
from app.rate_limits import limit_for
from app.services.draft_edges import run_draft_edges
from app.services.expand_aliases import run_expand_aliases
from app.services.extract_departments import run_extract
from app.services.locate import resolve_paths
from app.services.streetview_edges import run_streetview_edges
from app.services.url_safety import is_safe_external_url

router = APIRouter(tags=["jobs"])

_SLUG_PATTERN = re.compile(r"^[a-z0-9_]{2,64}$")


def _validate_slug(slug: str) -> None:
    if not _SLUG_PATTERN.match(slug):
        raise HTTPException(status_code=422, detail=f"Invalid slug '{slug}'.")
    facility_path, _topology_path, _source = resolve_paths(slug)
    if not facility_path.exists():
        raise HTTPException(status_code=404, detail=f"Facility '{slug}' not found")


class JobKickoffResponse(BaseModel):
    job_id: str
    slug: str
    stream_url: str


# ----- extract-departments -----

class ExtractDepartmentsRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64, pattern=_SLUG_PATTERN.pattern)
    urls: list[HttpUrl] = Field(..., min_length=1, max_length=20)
    model: str | None = None
    base_url: str | None = None


@router.post(
    "/extract-departments",
    response_model=JobKickoffResponse,
    status_code=202,
    dependencies=[Depends(demo_block)],
)
@limit_for("extract_departments")
async def extract_departments(
    request: Request,
    response: Response,
    req: ExtractDepartmentsRequest,
    user: CurrentUser = Depends(require_facility_editor),
) -> JobKickoffResponse:
    _ = user
    _ = request
    _ = response  # injected so slowapi can stamp rate-limit headers
    _validate_slug(req.slug)

    # Defense in depth against SSRF — Pydantic HttpUrl already blocked file://
    # and similar; this rejects URLs that resolve into the internal network.
    urls: list[str] = []
    for u in req.urls:
        url = str(u)
        ok, reason = is_safe_external_url(url)
        if not ok:
            raise HTTPException(status_code=400, detail=f"URL {url!r} rejected: {reason}")
        urls.append(url)

    job = jobs.create(kind="extract_departments")
    asyncio.create_task(
        run_extract(
            job,
            slug=req.slug,
            urls=urls,
            model=req.model,
            base_url=req.base_url,
        )
    )
    return JobKickoffResponse(job_id=job.id, slug=req.slug, stream_url=f"/jobs/{job.id}/stream")


# ----- draft-edges -----

class DraftEdgesRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64, pattern=_SLUG_PATTERN.pattern)
    max_dist: int = Field(default=800, ge=50, le=5000)


@router.post("/draft-edges", response_model=JobKickoffResponse, status_code=202)
async def draft_edges(
    req: DraftEdgesRequest,
    user: CurrentUser = Depends(require_facility_editor),
) -> JobKickoffResponse:
    _ = user
    _validate_slug(req.slug)
    job = jobs.create(kind="draft_edges")
    asyncio.create_task(run_draft_edges(job, slug=req.slug, max_dist=req.max_dist))
    return JobKickoffResponse(job_id=job.id, slug=req.slug, stream_url=f"/jobs/{job.id}/stream")


# ----- streetview-edges (bulk) -----

class StreetviewEdgesRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64, pattern=_SLUG_PATTERN.pattern)
    use_routing: bool = Field(default=True)
    image_call_cap: int = Field(default=500, ge=10, le=5000)


@router.post(
    "/streetview-edges",
    response_model=JobKickoffResponse,
    status_code=202,
    dependencies=[Depends(demo_block)],
)
@limit_for("streetview_edges_bulk")
async def streetview_edges_bulk(
    request: Request,
    response: Response,
    req: StreetviewEdgesRequest,
    user: CurrentUser = Depends(require_facility_editor),
) -> JobKickoffResponse:
    _ = user
    _ = request
    _ = response  # injected so slowapi can stamp rate-limit headers
    _validate_slug(req.slug)
    job = jobs.create(kind="streetview_edges")
    asyncio.create_task(
        run_streetview_edges(
            job,
            slug=req.slug,
            use_routing=req.use_routing,
            image_call_cap=req.image_call_cap,
        )
    )
    return JobKickoffResponse(job_id=job.id, slug=req.slug, stream_url=f"/jobs/{job.id}/stream")


# ----- expand-aliases -----

class ExpandAliasesRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64, pattern=_SLUG_PATTERN.pattern)
    model: str | None = None
    base_url: str | None = None


@router.post(
    "/expand-aliases",
    response_model=JobKickoffResponse,
    status_code=202,
    dependencies=[Depends(demo_block)],
)
@limit_for("expand_aliases")
async def expand_aliases(
    request: Request,
    response: Response,
    req: ExpandAliasesRequest,
    user: CurrentUser = Depends(require_facility_editor),
) -> JobKickoffResponse:
    _ = user
    _ = request
    _ = response  # injected so slowapi can stamp rate-limit headers
    _validate_slug(req.slug)
    job = jobs.create(kind="expand_aliases")
    asyncio.create_task(
        run_expand_aliases(job, slug=req.slug, model=req.model, base_url=req.base_url)
    )
    return JobKickoffResponse(job_id=job.id, slug=req.slug, stream_url=f"/jobs/{job.id}/stream")
