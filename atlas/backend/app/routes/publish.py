"""
POST /facilities/{slug}/publish — promotes a bootstrap draft to the published
data directory.

`FACILITIES_DIR` is symlinked to the Flutter app's bundled assets directory
(see paths.py), so publishing writes directly into what the on-device app
loads at build time. No separate mirror step.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import BaseModel

from app.auth import CurrentUser, require_admin
from app.locks import locks
from app.paths import BOOTSTRAP_DIR, FACILITIES_DIR
from app.services._io import read_json, write_json_atomic
from app.services.locate import osm_path_for
from app.services.proposals import personal_draft_dir
from app.services.publish import compute_warnings, validate_facility

router = APIRouter(prefix="/facilities", tags=["publish"])

_SLUG_PATTERN = r"^[a-z0-9_]{2,64}$"
SlugParam = Annotated[
    str,
    PathParam(pattern=_SLUG_PATTERN, min_length=2, max_length=64),
]


class PublishResponse(BaseModel):
    slug: str
    facility_path: str
    topology_path: str
    issues: list[str]
    warnings: list[str]


class DryRunResponse(BaseModel):
    slug: str
    issues: list[str]
    warnings: list[str]
    ok: bool


@router.get("/{slug}/publish/dry-run", response_model=DryRunResponse)
def dry_run(slug: SlugParam) -> DryRunResponse:
    """Run validation only — does not move files. The editor calls this to
    surface a checklist without committing. Warnings don't block publish."""
    facility, topology = _load_for_publish(slug)
    issues = validate_facility(facility, topology)
    warnings = compute_warnings(facility, topology)
    return DryRunResponse(slug=slug, issues=issues, warnings=warnings, ok=not issues)


class PublishRequest(BaseModel):
    """Optional flags. force=True bypasses validation issues (use sparingly)."""
    force: bool = False


@router.post("/{slug}/publish", response_model=PublishResponse)
def publish(
    slug: SlugParam,
    body: PublishRequest | None = None,
    user: CurrentUser = Depends(require_admin),
) -> PublishResponse:
    """Promote bootstrap → published. Refuses if validation fails unless force=True."""
    locks.assert_writable(slug, user.login, enforce=user.auth_enforced)
    body = body or PublishRequest()

    facility, topology = _load_for_publish(slug)
    return run_publish(slug=slug, facility=facility, topology=topology, force=body.force)


def run_publish(
    *,
    slug: str,
    facility: dict[str, Any],
    topology: dict[str, Any] | None,
    force: bool,
) -> PublishResponse:
    """Publish primitive shared by the admin /publish route and the proposal
    approve flow. Validates, normalizes ids, bakes OSM into topology, and writes
    to FACILITIES_DIR (which is symlinked to the Flutter assets dir)."""
    issues = validate_facility(facility, topology)
    if issues and not force:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Facility failed validation. Pass force=true to override.",
                "issues": issues,
            },
        )

    # Slug is authoritative — heal any drifted ids before writing so the
    # published JSON always agrees with the URL/filename.
    facility["id"] = slug
    if topology is not None:
        topology["facility_id"] = slug
        # Bake the OSM reference layer (building footprints + footways) into
        # the published topology so the on-device app can render an offline
        # mini-map without a tile server. Editor still reads OSM from the
        # bootstrap dir separately; this is purely additive for consumers.
        osm_src = osm_path_for(slug)
        if osm_src.exists():
            try:
                osm = read_json(osm_src)
                topology["osm"] = {
                    "features": osm.get("features") or [],
                    "footways": osm.get("footways") or [],
                }
            except Exception:  # noqa: BLE001
                # Non-fatal: publish still succeeds without OSM, the app just
                # falls back to a route-only sparkline.
                pass

    facility_out = FACILITIES_DIR / f"{slug}.json"
    topology_out = FACILITIES_DIR / f"{slug}.topology.json"
    write_json_atomic(facility_out, facility)
    if topology is not None:
        write_json_atomic(topology_out, topology)

    warnings: list[str] = list(compute_warnings(facility, topology))

    return PublishResponse(
        slug=slug,
        facility_path=str(facility_out),
        topology_path=str(topology_out),
        issues=issues if force else [],
        warnings=warnings,
    )


def _load_for_publish(slug: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Always read from the bootstrap dir if it exists — that's the workspace."""
    bootstrap_dir = BOOTSTRAP_DIR / slug
    facility_path = bootstrap_dir / "facility.json"
    topology_path = bootstrap_dir / "topology.json"
    if not facility_path.exists():
        # Fall back to already-published source. Lets a user re-publish
        # after editing in place.
        facility_path = FACILITIES_DIR / f"{slug}.json"
        topology_path = FACILITIES_DIR / f"{slug}.topology.json"
    if not facility_path.exists():
        raise HTTPException(status_code=404, detail=f"Facility '{slug}' not found")
    facility = read_json(facility_path)
    topology = read_json(topology_path) if topology_path.exists() else None
    return facility, topology


def load_for_proposal(slug: str, author: str, source: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Load facility + topology files for a proposed change. Mirrors
    `_load_for_publish` but reads from the proposal's source dir instead of
    falling back to the published version."""
    if source == "personal_draft":
        draft_dir = personal_draft_dir(author, slug)
        facility_path = draft_dir / "facility.json"
        topology_path = draft_dir / "topology.json"
    elif source == "shared_bootstrap":
        bootstrap_dir = BOOTSTRAP_DIR / slug
        facility_path = bootstrap_dir / "facility.json"
        topology_path = bootstrap_dir / "topology.json"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown proposal source: {source}")
    if not facility_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No proposal files for '{slug}' from '{author}'",
        )
    facility = read_json(facility_path)
    topology = read_json(topology_path) if topology_path.exists() else None
    return facility, topology
