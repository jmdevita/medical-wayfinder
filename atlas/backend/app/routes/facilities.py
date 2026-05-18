"""
Facility discovery, read, and write endpoints.

Source of truth is the filesystem. Published facilities live in
`health_wayfinder/assets/facilities/<slug>.json` (+ `.topology.json`) —
exposed to atlas via the symlink at `atlas/data/facilities/`. In-progress
drafts live in `tools/bootstrap/<slug>/{facility,topology}.json` — shared
with the `tools/` CLI runbook.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import BaseModel, Field

from app.auth import CurrentUser, require_facility_editor
from app.locks import locks
from app.paths import BOOTSTRAP_DIR, FACILITIES_DIR
from app.services.reroute import reroute as reroute_edges_service
from app.services.summarize import (
    build_mini_map,
    centroid,
    file_signature,
    humanize_age,
    infer_region,
    status_for,
)

router = APIRouter(prefix="/facilities", tags=["facilities"])

# Slugs are file-system path components, so they must not contain anything
# that could escape the data directory or smuggle whitespace/control chars.
# The bootstrap endpoint enforces the same shape on creation; this is the
# read/write defense-in-depth.
_SLUG_PATTERN = r"^[a-z0-9_]{2,64}$"
SlugParam = Annotated[
    str,
    PathParam(
        pattern=_SLUG_PATTERN,
        min_length=2,
        max_length=64,
        description="Lowercase letters, digits, and underscores only.",
    ),
]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write atomically: temp file + rename, so a crashed write never leaves a half-file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def _summarize(
    *,
    slug: str,
    facility: dict[str, Any],
    topology: dict[str, Any] | None,
    source: str,  # "published" or "bootstrap"
    facility_path: Path,
) -> dict[str, Any]:
    nodes_list = (topology or {}).get("nodes", [])
    edges_list = (topology or {}).get("edges", [])

    lat, lng = centroid(facility.get("buildings"), fallback=(0.0, 0.0))
    address = facility.get("address", "")
    mtime, by = file_signature(facility_path)

    return {
        "id": slug,
        "name": facility.get("name", slug),
        "address": address,
        "type": facility.get("type", ""),
        "region": infer_region(address),
        "nodes": len(nodes_list),
        "edges": len(edges_list),
        "depts": len(facility.get("departments", [])),
        "issues": 0,  # populated by the reports endpoint when it lands
        "status": status_for(source, edges_list),
        "updated": humanize_age(mtime),
        "by": by,
        "miniMap": build_mini_map(lat=lat, lng=lng, nodes=nodes_list, edges=edges_list),
    }


@router.get("")
def list_facilities() -> dict[str, list[dict[str, Any]]]:
    """One summary per known facility — published assets first, then drafts."""
    out: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    if FACILITIES_DIR.exists():
        for facility_path in sorted(FACILITIES_DIR.glob("*.json")):
            if facility_path.name.endswith(".topology.json"):
                continue
            slug = facility_path.stem
            try:
                facility = _read_json(facility_path)
            except json.JSONDecodeError:
                continue
            topology_path = FACILITIES_DIR / f"{slug}.topology.json"
            topology = _read_json(topology_path) if topology_path.exists() else None
            out.append(_summarize(
                slug=slug,
                facility=facility,
                topology=topology,
                source="published",
                facility_path=facility_path,
            ))
            seen_slugs.add(slug)

    if BOOTSTRAP_DIR.exists():
        for slug_dir in sorted(BOOTSTRAP_DIR.iterdir()):
            if not slug_dir.is_dir() or slug_dir.name in seen_slugs:
                continue
            facility_path = slug_dir / "facility.json"
            topology_path = slug_dir / "topology.json"
            if not facility_path.exists():
                continue
            try:
                facility = _read_json(facility_path)
            except json.JSONDecodeError:
                continue
            topology = _read_json(topology_path) if topology_path.exists() else None
            out.append(_summarize(
                slug=slug_dir.name,
                facility=facility,
                topology=topology,
                source="bootstrap",
                facility_path=facility_path,
            ))

    return {"facilities": out}


def _resolve_paths(slug: str) -> tuple[Path, Path, str]:
    """Return (facility_path, topology_path, source) for a slug."""
    bootstrap_dir = BOOTSTRAP_DIR / slug
    if bootstrap_dir.exists() and (bootstrap_dir / "facility.json").exists():
        return (
            bootstrap_dir / "facility.json",
            bootstrap_dir / "topology.json",
            "bootstrap",
        )
    return (
        FACILITIES_DIR / f"{slug}.json",
        FACILITIES_DIR / f"{slug}.topology.json",
        "published",
    )


@router.get("/{slug}")
def get_facility(slug: SlugParam) -> dict[str, Any]:
    """Return facility + topology for a slug."""
    facility_path, topology_path, source = _resolve_paths(slug)
    if not facility_path.exists():
        raise HTTPException(status_code=404, detail=f"Facility '{slug}' not found")
    return {
        "slug": slug,
        "source": source,
        "facility": _read_json(facility_path),
        "topology": _read_json(topology_path) if topology_path.exists() else None,
    }


# Generous caps that comfortably fit a major medical center while bounding
# memory pressure on PUT. (Mass General is the largest in our sample at 30
# nodes — these are 5–10× headroom.)
_MAX_NODES = 1000
_MAX_EDGES = 4000
_MAX_KEYWORDS_PER_NODE = 50
_MAX_INSTRUCTION_CHARS = 4000


class TopologyPayload(BaseModel):
    """Shape we accept on PUT. The schema validator runs on each save."""

    version: str = Field(..., min_length=1, max_length=64)
    facility_id: str = Field(..., pattern=_SLUG_PATTERN)
    nodes: list[dict[str, Any]] = Field(..., max_length=_MAX_NODES)
    edges: list[dict[str, Any]] = Field(..., max_length=_MAX_EDGES)


def _validate_payload_shape(payload: TopologyPayload) -> None:
    """
    Cheap structural checks beyond Pydantic — keeps malformed topologies from
    being persisted and confusing the editor on next load.
    """
    node_ids: set[str] = set()
    for n in payload.nodes:
        nid = n.get("id")
        if not isinstance(nid, str) or not nid:
            raise HTTPException(status_code=422, detail="Every node needs a non-empty 'id' string")
        if nid in node_ids:
            raise HTTPException(status_code=422, detail=f"Duplicate node id: {nid}")
        node_ids.add(nid)
        kw = n.get("keywords")
        if kw is not None and (not isinstance(kw, list) or len(kw) > _MAX_KEYWORDS_PER_NODE):
            raise HTTPException(status_code=422, detail=f"Node '{nid}' has too many keywords")
    for i, e in enumerate(payload.edges):
        f, t = e.get("from"), e.get("to")
        if f not in node_ids or t not in node_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Edge {i} references unknown node ({f!r} → {t!r})",
            )
        instr = e.get("instruction")
        if isinstance(instr, str) and len(instr) > _MAX_INSTRUCTION_CHARS:
            raise HTTPException(
                status_code=422,
                detail=f"Edge {i} instruction exceeds {_MAX_INSTRUCTION_CHARS} chars",
            )


@router.put("/{slug}/topology")
def save_topology(
    slug: SlugParam,
    payload: TopologyPayload,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    locks.assert_writable(slug, user.login, enforce=user.auth_enforced)
    """Persist a topology JSON edit. The URL slug is authoritative — the
    payload's facility_id is normalized to it on write so a client that
    sends a stale or wrong id never silently corrupts the file."""
    _validate_payload_shape(payload)

    facility_path, topology_path, _source = _resolve_paths(slug)
    if not facility_path.exists():
        raise HTTPException(status_code=404, detail=f"Facility '{slug}' not found")

    data = payload.model_dump()
    data["facility_id"] = slug
    _write_json(topology_path, data)
    return {
        "slug": slug,
        "saved_to": str(topology_path),
        "nodes": len(payload.nodes),
        "edges": len(payload.edges),
    }


_MAX_DEPARTMENTS = 500
_MAX_BUILDINGS = 200
_MAX_PARKING = 100
_MAX_TRANSIT = 100


@router.get("/{slug}/osm")
def get_osm(slug: SlugParam) -> dict[str, Any]:
    """
    Return the facility's OSM reference layer if it exists. Each `feature`
    has `polygon` + `tags` (building/amenity/healthcare/name); `footways`
    are linestrings of [lat, lng] pairs. The editor's layer toggles read
    these to render footprints and the footway graph.
    """
    from app.services.locate import osm_path_for
    osm_path = osm_path_for(slug)
    if not osm_path.exists():
        return {"slug": slug, "available": False, "features": [], "footways": []}
    osm = _read_json(osm_path)
    return {
        "slug": slug,
        "available": True,
        "features": osm.get("features") or [],
        "footways": osm.get("footways") or [],
    }


class BuildingPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    nearest_buildings: list[str] | None = Field(default=None, max_length=20)
    model_config = {"extra": "allow"}


class ParkingPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    nearest_buildings: list[str] | None = Field(default=None, max_length=20)
    model_config = {"extra": "allow"}


class TransitPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    model_config = {"extra": "allow"}


class MetadataPayload(BaseModel):
    """
    Facility metadata + structural lists (buildings/parking/transit). Departments
    have their own endpoint; topology has its own. This split keeps each save
    surface narrow so concurrent edits don't clobber each other.
    """
    name: str = Field(..., min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=400)
    type: str | None = Field(default=None, max_length=120)
    main_phone: str | None = Field(default=None, max_length=60)
    campus_description: str | None = Field(default=None, max_length=4000)
    buildings: list[BuildingPayload] = Field(default_factory=list, max_length=_MAX_BUILDINGS)
    parking:   list[ParkingPayload]  = Field(default_factory=list, max_length=_MAX_PARKING)
    transit:   list[TransitPayload]  = Field(default_factory=list, max_length=_MAX_TRANSIT)
    model_config = {"extra": "allow"}


@router.put("/{slug}/metadata")
def save_metadata(
    slug: SlugParam,
    payload: MetadataPayload,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    locks.assert_writable(slug, user.login, enforce=user.auth_enforced)
    """Save facility metadata and structural lists, preserving departments + id."""
    facility_path, _topology_path, _source = _resolve_paths(slug)
    if not facility_path.exists():
        raise HTTPException(status_code=404, detail=f"Facility '{slug}' not found")
    facility = _read_json(facility_path)

    # Merge: pull in payload fields, keep existing departments. The URL slug
    # is authoritative for `id` — overwrite any drifted value on disk so the
    # editor and on-device app agree on a single identifier.
    incoming = {k: v for k, v in payload.model_dump().items() if v is not None}
    facility["id"] = slug
    # Only persist non-empty lists explicitly; empty arrays still overwrite.
    facility["name"] = incoming["name"]
    for key in ("address", "type", "main_phone", "campus_description"):
        if key in incoming:
            facility[key] = incoming[key]
        else:
            facility.pop(key, None)
    facility["buildings"] = incoming.get("buildings", [])
    if incoming.get("parking") is not None:
        facility["parking"] = incoming["parking"]
    if incoming.get("transit") is not None:
        facility["transit"] = incoming["transit"]

    _write_json(facility_path, facility)
    return {
        "slug": slug,
        "saved_to": str(facility_path),
        "buildings": len(facility.get("buildings", [])),
        "parking":   len(facility.get("parking", [])),
        "transit":   len(facility.get("transit", [])),
    }


class DepartmentPayload(BaseModel):
    """One row in the facility's departments[] list. Loose by design — the
    editor passes through fields it doesn't understand (e.g. confidence,
    source) so the round-trip never strips data."""
    name: str = Field(..., min_length=1, max_length=200)
    building: str | None = Field(default=None, max_length=200)
    floor: str | None = Field(default=None, max_length=120)
    topology_node_id: str | None = Field(default=None, max_length=64)
    aliases: list[str] | None = Field(default=None, max_length=50)
    hours: str | None = Field(default=None, max_length=200)
    check_in: str | None = Field(default=None, max_length=400)
    directions: str | None = Field(default=None, max_length=2000)
    confidence: str | None = Field(default=None, max_length=32)
    source: str | None = Field(default=None, max_length=400)
    accessible: bool | None = None

    model_config = {"extra": "allow"}


class DepartmentsPayload(BaseModel):
    departments: list[DepartmentPayload] = Field(..., max_length=_MAX_DEPARTMENTS)


@router.put("/{slug}/departments")
def save_departments(
    slug: SlugParam,
    payload: DepartmentsPayload,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    locks.assert_writable(slug, user.login, enforce=user.auth_enforced)
    """Persist a department-list edit. Cross-checks topology_node_id against
    the current topology; rejects assignments to nonexistent nodes and
    duplicate department names."""
    facility_path, topology_path, _source = _resolve_paths(slug)
    if not facility_path.exists():
        raise HTTPException(status_code=404, detail=f"Facility '{slug}' not found")

    # Reject duplicate names — they break the orchestrator's by-name lookup
    # and the editor UI uses name as identity in a few places.
    name_counts: dict[str, int] = {}
    for d in payload.departments:
        name_counts[d.name] = name_counts.get(d.name, 0) + 1
    dups = [n for n, c in name_counts.items() if c > 1]
    if dups:
        raise HTTPException(
            status_code=422,
            detail=f"Duplicate department names: {', '.join(dups[:5])}"
                   + (" …" if len(dups) > 5 else ""),
        )

    # Cross-check: every topology_node_id must exist in the current topology.
    node_ids: set[str] = set()
    if topology_path.exists():
        topology = _read_json(topology_path)
        node_ids = {n.get("id") for n in topology.get("nodes", []) if isinstance(n.get("id"), str)}
    bad = [
        d.name for d in payload.departments
        if d.topology_node_id and node_ids and d.topology_node_id not in node_ids
    ]
    if bad:
        raise HTTPException(
            status_code=422,
            detail=f"These departments pin missing topology nodes: {', '.join(bad[:5])}"
                   + (" …" if len(bad) > 5 else ""),
        )

    facility = _read_json(facility_path)
    facility["departments"] = [
        {k: v for k, v in d.model_dump().items() if v is not None}
        for d in payload.departments
    ]
    _write_json(facility_path, facility)
    return {
        "slug": slug,
        "saved_to": str(facility_path),
        "departments": len(payload.departments),
    }


class RerouteRequest(BaseModel):
    """Empty body re-routes every stale edge; pass indices to target specific ones."""
    edge_indices: list[int] | None = Field(default=None, max_length=4000)


@router.post("/{slug}/reroute-edges")
def reroute_edges(
    slug: SlugParam,
    body: RerouteRequest | None = None,
    user: CurrentUser = Depends(require_facility_editor),
) -> dict[str, Any]:
    locks.assert_writable(slug, user.login, enforce=user.auth_enforced)
    """Re-route stale (or specified) edges via the OSM footway graph."""
    body = body or RerouteRequest()
    try:
        return reroute_edges_service(slug=slug, edge_indices=body.edge_indices)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
