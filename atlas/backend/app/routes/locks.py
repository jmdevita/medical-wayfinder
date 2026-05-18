"""
GET    /facilities/{slug}/lock   — current state (or null)
POST   /facilities/{slug}/lock   — acquire or heartbeat
DELETE /facilities/{slug}/lock   — release if you hold it

Frontend lifecycle:
  - editor mounts                → POST acquire
  - every 60s while editing      → POST heartbeat (same endpoint)
  - editor unmounts / navigates  → DELETE release (best-effort)
  - mutation 423-d                → bail out and surface the holder
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path as PathParam

from app.auth import CurrentUser, require_facility_editor
from app.locks import LOCK_TTL_SECONDS, locks

router = APIRouter(prefix="/facilities", tags=["locks"])

_SLUG_PATTERN = r"^[a-z0-9_]{2,64}$"
SlugParam = Annotated[str, PathParam(pattern=_SLUG_PATTERN, min_length=2, max_length=64)]


@router.get("/{slug}/lock")
def lock_status(slug: SlugParam) -> dict[str, object]:
    state = locks.status(slug)
    if not state:
        return {"slug": slug, "locked": False, "ttl_seconds": LOCK_TTL_SECONDS}
    return {
        "slug": slug,
        "locked": True,
        "held_by": state.user,
        "acquired_at": state.acquired_at,
        "last_heartbeat": state.last_heartbeat,
        "ttl_seconds": LOCK_TTL_SECONDS,
    }


@router.post("/{slug}/lock")
def acquire_lock(
    slug: SlugParam,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, object]:
    state = locks.acquire_or_heartbeat(slug, user.login)
    return {
        "slug": slug,
        "held_by": state.user,
        "acquired_at": state.acquired_at,
        "last_heartbeat": state.last_heartbeat,
    }


@router.delete("/{slug}/lock")
def release_lock(
    slug: SlugParam,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, object]:
    released = locks.release(slug, user.login)
    return {"slug": slug, "released": released}
