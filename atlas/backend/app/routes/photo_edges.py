"""Photo edge-walker routes: upload, list, reorder, caption, delete, generate,
and an authenticated proxy for serving persisted JPEGs.

All routes are gated by ``require_facility_editor``. Photos
are persisted under ``BOOTSTRAP_DIR/<slug>/photos/<edge_id>/`` with EXIF
stripped except a small whitelist (see ``_io.safe_image_write``).
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth import CurrentUser, require_facility_editor
from app.locks import locks
from app.rate_limits import limit_for
from app.services.locate import resolve_paths
from app.services.photo_edges import (
    ACCEPTED_MIME,
    MAX_BYTES_PER_PHOTO,
    MAX_PHOTOS_PER_EDGE,
    delete_all_edge_photos,
    delete_all_node_photos,
    delete_node_photo,
    delete_photo,
    generate_from_photos,
    list_node_photos,
    list_photos,
    photo_path,
    reorder_node_photos,
    reorder_photos,
    save_uploaded_node_photo,
    save_uploaded_photo,
    update_caption,
    update_node_caption,
)
from app.services.streetview_edges import scrub_secrets

router = APIRouter(tags=["photo-edges"])

_SLUG_PATTERN = re.compile(r"^[a-z0-9_]{2,64}$")
_NODE_ID_PATTERN = re.compile(r"^[a-z0-9_]{1,80}$")
_PHOTO_ID_PATTERN = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$"
)


def _validate_slug(slug: str) -> None:
    if not _SLUG_PATTERN.match(slug):
        raise HTTPException(status_code=422, detail=f"Invalid slug '{slug}'.")
    facility_path, _topology_path, _source = resolve_paths(slug)
    if not facility_path.exists():
        raise HTTPException(status_code=404, detail=f"Facility '{slug}' not found")


def _validate_node_id(name: str, value: str) -> None:
    if not _NODE_ID_PATTERN.match(value):
        raise HTTPException(status_code=422, detail=f"Invalid {name}: {value!r}")


def _validate_photo_id(value: str) -> None:
    if not _PHOTO_ID_PATTERN.match(value):
        raise HTTPException(status_code=422, detail=f"Invalid photo_id {value!r}.")


# --- Upload ---------------------------------------------------------------

@router.post("/photo-edges/{slug}/edges/{from_id}/{to_id}/photos")
@limit_for("photo_edges_upload")
async def upload_photo(
    request: Request,
    response: Response,
    slug: str,
    from_id: str,
    to_id: str,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    consent: bool = Form(...),
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = request
    _ = response  # injected so slowapi can stamp rate-limit headers
    _validate_slug(slug)
    _validate_node_id("from_id", from_id)
    _validate_node_id("to_id", to_id)

    if not consent:
        raise HTTPException(
            status_code=422,
            detail="Consent flag must be true. You must affirm you have the "
                   "right to share these photos.",
        )

    # MIME check first — cheap and rejects obvious mismatches before reading.
    if (file.content_type or "").lower() not in ACCEPTED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Only JPEG / HEIC uploads are accepted (got {file.content_type!r}).",
        )

    # Bound the read so a 5GB upload can't OOM the worker.
    raw = await file.read(MAX_BYTES_PER_PHOTO + 1)
    if len(raw) > MAX_BYTES_PER_PHOTO:
        raise HTTPException(
            status_code=413,
            detail=f"Photo exceeds {MAX_BYTES_PER_PHOTO // (1024 * 1024)}MB cap.",
        )

    try:
        entry = save_uploaded_photo(
            slug=slug, from_id=from_id, to_id=to_id,
            raw=raw,
            filename=file.filename or "upload.jpg",
            caption=caption,
            consent=consent,
            uploaded_by=user.login,
        )
    except ValueError as exc:
        # Distinguish "too many photos" (409) from other validation errors (422).
        text = str(exc)
        if "cap" in text and str(MAX_PHOTOS_PER_EDGE) in text:
            raise HTTPException(status_code=409, detail=text) from exc
        raise HTTPException(status_code=422, detail=text) from exc
    return {"slug": slug, "from": from_id, "to": to_id, "photo": entry}


# --- List -----------------------------------------------------------------

@router.get("/photo-edges/{slug}/edges/{from_id}/{to_id}/photos")
async def list_edge_photos(
    slug: str,
    from_id: str,
    to_id: str,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _validate_slug(slug)
    _validate_node_id("from_id", from_id)
    _validate_node_id("to_id", to_id)
    return {
        "slug": slug, "from": from_id, "to": to_id,
        "photos": list_photos(slug, from_id, to_id),
    }


# --- Reorder --------------------------------------------------------------

class ReorderRequest(BaseModel):
    photo_ids: list[str] = Field(..., min_length=0, max_length=MAX_PHOTOS_PER_EDGE)


@router.patch("/photo-edges/{slug}/edges/{from_id}/{to_id}/photos/order")
async def reorder_edge_photos(
    slug: str,
    from_id: str,
    to_id: str,
    req: ReorderRequest,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _validate_slug(slug)
    _validate_node_id("from_id", from_id)
    _validate_node_id("to_id", to_id)
    for pid in req.photo_ids:
        _validate_photo_id(pid)
    try:
        photos = reorder_photos(slug, from_id, to_id, req.photo_ids)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"slug": slug, "from": from_id, "to": to_id, "photos": photos}


# --- Caption update -------------------------------------------------------

class CaptionRequest(BaseModel):
    caption: str | None = Field(default=None, max_length=500)


@router.patch("/photo-edges/{slug}/edges/{from_id}/{to_id}/photos/{photo_id}")
async def update_photo_caption(
    slug: str,
    from_id: str,
    to_id: str,
    photo_id: str,
    req: CaptionRequest,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _validate_slug(slug)
    _validate_node_id("from_id", from_id)
    _validate_node_id("to_id", to_id)
    _validate_photo_id(photo_id)
    try:
        entry = update_caption(slug, from_id, to_id, photo_id, req.caption)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"photo": entry}


# --- Delete ---------------------------------------------------------------

@router.delete("/photo-edges/{slug}/edges/{from_id}/{to_id}/photos/{photo_id}")
async def delete_edge_photo(
    slug: str,
    from_id: str,
    to_id: str,
    photo_id: str,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _validate_slug(slug)
    _validate_node_id("from_id", from_id)
    _validate_node_id("to_id", to_id)
    _validate_photo_id(photo_id)
    try:
        remaining = delete_photo(slug, from_id, to_id, photo_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"slug": slug, "from": from_id, "to": to_id, "remaining": remaining}


# --- Node photo routes (Phase 2) -----------------------------------------

@router.post("/photo-edges/{slug}/nodes/{node_id}/photos")
@limit_for("photo_edges_upload")
async def upload_node_photo(
    request: Request,
    response: Response,
    slug: str,
    node_id: str,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    consent: bool = Form(...),
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = request
    _ = response  # injected so slowapi can stamp rate-limit headers
    _validate_slug(slug)
    _validate_node_id("node_id", node_id)
    if not consent:
        raise HTTPException(status_code=422, detail="Consent flag must be true.")
    if (file.content_type or "").lower() not in ACCEPTED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Only JPEG / HEIC uploads are accepted (got {file.content_type!r}).",
        )
    raw = await file.read(MAX_BYTES_PER_PHOTO + 1)
    if len(raw) > MAX_BYTES_PER_PHOTO:
        raise HTTPException(
            status_code=413,
            detail=f"Photo exceeds {MAX_BYTES_PER_PHOTO // (1024 * 1024)}MB cap.",
        )
    try:
        entry = save_uploaded_node_photo(
            slug=slug, node_id=node_id,
            raw=raw,
            filename=file.filename or "upload.jpg",
            caption=caption, consent=consent,
            uploaded_by=user.login,
        )
    except ValueError as exc:
        text = str(exc)
        if "cap" in text and str(MAX_PHOTOS_PER_EDGE) in text:
            raise HTTPException(status_code=409, detail=text) from exc
        raise HTTPException(status_code=422, detail=text) from exc
    return {"slug": slug, "node_id": node_id, "photo": entry}


@router.get("/photo-edges/{slug}/nodes/{node_id}/photos")
async def list_node_photos_route(
    slug: str,
    node_id: str,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _validate_slug(slug)
    _validate_node_id("node_id", node_id)
    return {"slug": slug, "node_id": node_id, "photos": list_node_photos(slug, node_id)}


@router.patch("/photo-edges/{slug}/nodes/{node_id}/photos/order")
async def reorder_node_photos_route(
    slug: str,
    node_id: str,
    req: ReorderRequest,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _validate_slug(slug)
    _validate_node_id("node_id", node_id)
    for pid in req.photo_ids:
        _validate_photo_id(pid)
    try:
        photos = reorder_node_photos(slug, node_id, req.photo_ids)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"slug": slug, "node_id": node_id, "photos": photos}


@router.patch("/photo-edges/{slug}/nodes/{node_id}/photos/{photo_id}")
async def update_node_photo_caption(
    slug: str,
    node_id: str,
    photo_id: str,
    req: CaptionRequest,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _validate_slug(slug)
    _validate_node_id("node_id", node_id)
    _validate_photo_id(photo_id)
    try:
        entry = update_node_caption(slug, node_id, photo_id, req.caption)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"photo": entry}


@router.delete("/photo-edges/{slug}/nodes/{node_id}/photos/{photo_id}")
async def delete_node_photo_route(
    slug: str,
    node_id: str,
    photo_id: str,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _validate_slug(slug)
    _validate_node_id("node_id", node_id)
    _validate_photo_id(photo_id)
    try:
        remaining = delete_node_photo(slug, node_id, photo_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"slug": slug, "node_id": node_id, "remaining": remaining}


# --- Cascade delete (orphan cleanup) -------------------------------------

@router.delete("/photo-edges/{slug}/edges/{from_id}/{to_id}/photos")
async def delete_all_edge_photos_route(
    slug: str,
    from_id: str,
    to_id: str,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    """Wipe every photo attached to an edge. Used on edge deletion so the
    on-disk dir doesn't outlive the topology entry."""
    _ = user
    _validate_slug(slug)
    _validate_node_id("from_id", from_id)
    _validate_node_id("to_id", to_id)
    removed = delete_all_edge_photos(slug, from_id, to_id)
    return {"slug": slug, "from": from_id, "to": to_id, "removed": removed}


@router.delete("/photo-edges/{slug}/nodes/{node_id}/photos")
async def delete_all_node_photos_route(
    slug: str,
    node_id: str,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    """Wipe every photo attached to a node. Used on node deletion."""
    _ = user
    _validate_slug(slug)
    _validate_node_id("node_id", node_id)
    try:
        removed = delete_all_node_photos(slug, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"slug": slug, "node_id": node_id, "removed": removed}


# --- Generate -------------------------------------------------------------

@router.post("/photo-edges/{slug}/edges/{from_id}/{to_id}/generate")
@limit_for("photo_edges_generate")
async def generate_photo_suggestion(
    request: Request,
    response: Response,
    slug: str,
    from_id: str,
    to_id: str,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    _ = user
    _ = request
    _ = response  # injected so slowapi can stamp rate-limit headers
    _validate_slug(slug)
    _validate_node_id("from_id", from_id)
    _validate_node_id("to_id", to_id)
    # Same lock contract as accept/PUT topology — generation reads photos but
    # writes a suggestion sidecar that pairs with topology mutations on accept.
    locks.assert_writable(slug, user.login, enforce=user.auth_enforced)
    try:
        suggestion = await generate_from_photos(
            slug=slug, from_id=from_id, to_id=to_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=scrub_secrets(str(exc))) from exc
    return suggestion


# --- Photo proxy ----------------------------------------------------------

@router.get("/photo-edges/{slug}/photos/{photo_id}.jpg")
@limit_for("photo_edges_photo")
async def photo_proxy(
    request: Request,
    response: Response,
    slug: str,
    photo_id: str,
    user: CurrentUser = Depends(require_facility_editor),
) -> FileResponse:
    _ = user
    _ = request
    _ = response  # injected so slowapi can stamp rate-limit headers
    _validate_slug(slug)
    _validate_photo_id(photo_id)
    p = photo_path(slug, photo_id)
    if p is None or not p.exists():
        raise HTTPException(status_code=404, detail=f"Photo {photo_id} not found.")
    # We own the bytes (re-encoded on upload), so a private cache is safe and
    # cuts repeat-fetch traffic during lightbox browsing.
    return FileResponse(
        p, media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
