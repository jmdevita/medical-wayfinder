"""Async wrapper around the Street View edge-walker POC.

Reuses streetview_poc/poc/* directly (sampler, routing, streetview, coverage,
vision). The bulk job
walks every edge whose instruction is empty or starts with "TODO:", runs a
free metadata sweep + coverage check, and only fetches images + calls the
vision model for edges that pass the gate.

Suggestions land in `tools/bootstrap/<slug>/suggestions.json` (the
sidecar — topology schema is unchanged). Approving a suggestion replaces
the topology edge's `instruction` field and removes the sidecar entry.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx


# --- Secret scrubbing -----------------------------------------------------

_KEY_PARAM_RE = re.compile(r"([?&](?:key|api_key)=)[^&\s]+", re.IGNORECASE)


def scrub_secrets(text: str) -> str:
    """Replace `key=...` / `api_key=...` query params with REDACTED.

    httpx exception messages and Google API error bodies often include the
    full request URL with the API key. Anything that propagates such a
    message back to the editor (SSE stream, HTTP response detail) MUST go
    through this scrubber first.
    """
    if not text:
        return text
    return _KEY_PARAM_RE.sub(r"\1REDACTED", text)

from app.jobs import Job
from app.services._io import (
    ensure_streetview_poc_on_path,
    read_json,
    write_json_atomic,
)
from app.services.locate import resolve_paths, suggestions_path_for


# --- Eligibility ----------------------------------------------------------

def _eligible(edge: dict[str, Any]) -> bool:
    """Bulk fills only edges with empty or TODO-stub instructions. Real
    human-authored prose is left alone."""
    inst = (edge.get("instruction") or "").strip()
    return inst == "" or inst.startswith("TODO:")


def _suggestions_index(sidecar: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(s["from"], s["to"]): s for s in sidecar.get("suggestions", [])}


def _empty_sidecar(slug: str) -> dict[str, Any]:
    return {
        "slug": slug,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suggestions": [],
    }


# --- Per-edge generation (shared by bulk + sync routes) -------------------

async def _generate_for_edge(
    *,
    slug: str,
    from_node: dict[str, Any],
    to_node: dict[str, Any],
    api_key: str,
    interval_m: float = 20.0,
    use_routing: bool = True,
    http: httpx.Client | None = None,
) -> dict[str, Any] | None:
    """Run the metadata sweep, coverage check, image fetch, and vision call
    for a single edge. Returns a suggestion dict ready to insert into the
    sidecar, or None if coverage failed (caller decides whether to skip)."""
    ensure_streetview_poc_on_path()
    from streetview_poc.poc import sampler, streetview, vision  # noqa: E402
    from streetview_poc.poc.coverage import assess  # noqa: E402
    from streetview_poc.poc.routing import (  # noqa: E402
        resample_polyline,
        route_polyline,
    )

    start = (from_node["lat"], from_node["lng"])
    end = (to_node["lat"], to_node["lng"])

    # Phase 1: routing (or straight-line fallback)
    routing_used = "straight_line"
    routed = None
    if use_routing:
        try:
            routed = await asyncio.to_thread(route_polyline, slug, start, end)
        except Exception:
            routed = None
        if routed:
            waypoints = resample_polyline(routed, interval_m=interval_m)
            routing_used = "osm_footway"
        else:
            waypoints = sampler.interpolate_polyline(start, end, interval_m=interval_m)
    else:
        waypoints = sampler.interpolate_polyline(start, end, interval_m=interval_m)
    headings = sampler.headings_for(waypoints)
    routed_m = (
        sum(sampler.haversine_m(routed[i], routed[i + 1])
            for i in range(len(routed) - 1)) if routed else None
    )

    # Phase 2: metadata sweep (free)
    samples: list[dict[str, Any]] = []
    seen: set[str] = set()
    owns_http = http is None
    client = http or httpx.Client(timeout=30.0)
    try:
        for (lat, lng), heading in zip(waypoints, headings):
            meta = await asyncio.to_thread(
                streetview.metadata, lat, lng,
                api_key=api_key, client=client,
            )
            if meta is None:
                samples.append({
                    "lat": lat, "lng": lng, "heading": heading,
                    "pano_id": None, "pano_date": None, "skipped": "no_pano",
                })
                continue
            sample = {
                "lat": lat, "lng": lng, "heading": heading,
                "pano_id": meta.pano_id, "pano_date": meta.date,
                "pano_lat": meta.lat, "pano_lng": meta.lng,
            }
            if meta.pano_id in seen:
                sample["skipped"] = "duplicate_pano"
            else:
                seen.add(meta.pano_id)
            samples.append(sample)

        # Phase 3: coverage assessment (free)
        verdict = assess(samples, destination=end)
        if verdict.verdict == "fail":
            return {
                "from": from_node["id"],
                "to": to_node["id"],
                "source": "streetview",
                "instruction": None,
                "landmarks": [],
                "routing": {
                    "method": routing_used,
                    "routed_m": round(routed_m, 1) if routed_m is not None else None,
                    "polyline_points": len(routed) if routed else None,
                },
                "coverage": {
                    "verdict": verdict.verdict,
                    "metrics": verdict.metrics,
                    "reasons": verdict.reasons,
                },
                "evidence": {"pano_ids": [], "pano_dates": [], "model": None},
                "skipped_reason": "coverage_fail",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # Phase 4: image fetch (billed; only on PASS / WARN)
        images: list[bytes] = []
        used_panos: list[str] = []
        used_dates: list[str | None] = []
        for s in samples:
            if not s.get("pano_id") or s.get("skipped"):
                continue
            jpeg = await asyncio.to_thread(
                streetview.image_bytes,
                api_key=api_key, heading=s["heading"],
                pano_id=s["pano_id"], client=client,
            )
            images.append(jpeg)
            used_panos.append(s["pano_id"])
            used_dates.append(s.get("pano_date"))

        if not images:
            return {
                "from": from_node["id"],
                "to": to_node["id"],
                "source": "streetview",
                "instruction": None,
                "landmarks": [],
                "routing": {
                    "method": routing_used,
                    "routed_m": round(routed_m, 1) if routed_m is not None else None,
                    "polyline_points": len(routed) if routed else None,
                },
                "coverage": {
                    "verdict": verdict.verdict,
                    "metrics": verdict.metrics,
                    "reasons": verdict.reasons,
                },
                "evidence": {"pano_ids": [], "pano_dates": [], "model": None},
                "skipped_reason": "no_images_after_filter",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # Phase 5: vision call
        from_label = from_node.get("label", from_node["id"])
        result = await vision.describe_walk(images, from_label=from_label)

    finally:
        if owns_http:
            client.close()

    return {
        "from": from_node["id"],
        "to": to_node["id"],
        "source": "streetview",
        "instruction": result.get("instruction", ""),
        "landmarks": result.get("landmarks", []),
        "routing": {
            "method": routing_used,
            "routed_m": round(routed_m, 1) if routed_m else None,
            "polyline_points": len(routed) if routed else None,
        },
        "coverage": {
            "verdict": verdict.verdict,
            "metrics": verdict.metrics,
            "reasons": verdict.reasons,
        },
        "evidence": {
            "pano_ids": used_panos,
            "pano_dates": used_dates,
            "model": vision.VISION_MODEL,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _require_api_key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not set.")
    return key


def load_suggestions(slug: str) -> dict[str, Any]:
    """Read the sidecar, returning an empty shell if absent. Pure function;
    callers acquire locks before mutation."""
    path = suggestions_path_for(slug)
    if not path.exists():
        return _empty_sidecar(slug)
    return read_json(path)


def save_suggestions(slug: str, sidecar: dict[str, Any]) -> None:
    sidecar["generated_at"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(suggestions_path_for(slug), sidecar)


def upsert_suggestion(slug: str, suggestion: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace a single suggestion. Returns the new sidecar."""
    sidecar = load_suggestions(slug)
    idx = _suggestions_index(sidecar)
    idx[(suggestion["from"], suggestion["to"])] = suggestion
    sidecar["suggestions"] = list(idx.values())
    save_suggestions(slug, sidecar)
    return sidecar


def remove_suggestion(slug: str, from_id: str, to_id: str) -> dict[str, Any]:
    """Remove a single suggestion entry. No-op if it doesn't exist."""
    sidecar = load_suggestions(slug)
    sidecar["suggestions"] = [
        s for s in sidecar.get("suggestions", [])
        if not (s["from"] == from_id and s["to"] == to_id)
    ]
    save_suggestions(slug, sidecar)
    return sidecar


def accept_suggestion(
    slug: str, from_id: str, to_id: str, *,
    replace_geometry: bool = True,
) -> dict[str, Any]:
    """Replace the topology edge's instruction with the suggestion's text and
    remove the sidecar entry. For user_photos suggestions with a derived
    polyline AND replace_geometry=True, also replace the edge's geometry.

    `replace_geometry` defaults to True so callers that don't pass the flag
    get the historical behavior. Streetview-source suggestions ignore the
    flag — they never write geometry regardless.

    Raises if no matching suggestion or edge exists.
    """
    sidecar = load_suggestions(slug)
    suggestion = next(
        (s for s in sidecar.get("suggestions", [])
         if s["from"] == from_id and s["to"] == to_id),
        None,
    )
    if suggestion is None:
        raise LookupError(f"No suggestion for {from_id} -> {to_id}")
    if not suggestion.get("instruction"):
        raise ValueError(
            f"Suggestion for {from_id} -> {to_id} has no instruction "
            f"(skipped due to coverage_fail or no_images_after_filter)."
        )

    _facility_path, topology_path, _source = resolve_paths(slug)
    if not topology_path.exists():
        raise FileNotFoundError(f"No topology.json for slug '{slug}'.")
    topology = read_json(topology_path)
    matched = False
    geometry_replaced = False
    source = suggestion.get("source", "streetview")
    photo_meta = suggestion.get("photo_metadata") or {}
    polyline = (
        photo_meta.get("suggested_polyline")
        if source == "user_photos" and replace_geometry
        else None
    )
    for e in topology.get("edges", []):
        if e["from"] == from_id and e["to"] == to_id:
            e["instruction"] = suggestion["instruction"]
            if polyline and len(polyline) >= 2:
                e["geometry"] = polyline
                geometry_replaced = True
            matched = True
            break
    if not matched:
        raise LookupError(f"No edge {from_id} -> {to_id} in topology.")
    write_json_atomic(topology_path, topology)
    remove_suggestion(slug, from_id, to_id)
    return {
        "topology_path": str(topology_path),
        "instruction": suggestion["instruction"],
        "geometry_replaced": geometry_replaced,
        "source": source,
    }


# --- Bulk job -------------------------------------------------------------

async def run_streetview_edges(
    job: Job,
    *,
    slug: str,
    interval_m: float = 20.0,
    use_routing: bool = True,
    image_call_cap: int = 500,
) -> None:
    """Iterate eligible edges, run coverage + vision per edge, write sidecar."""
    try:
        await job.emit("starting", 0.05, f"Suggesting Street View instructions for '{slug}'")
        api_key = _require_api_key()

        _facility_path, topology_path, _source = resolve_paths(slug)
        if not topology_path.exists():
            raise FileNotFoundError(f"No topology.json for slug '{slug}'.")
        topology = read_json(topology_path)
        nodes_by_id = {n["id"]: n for n in topology.get("nodes", [])}
        all_edges = list(topology.get("edges", []))

        eligible = [e for e in all_edges if _eligible(e)]
        already_authored = len(all_edges) - len(eligible)

        await job.emit(
            "metadata_sweep", 0.10,
            f"Scanning {len(eligible)} eligible edges (skipping {already_authored} already authored)",
        )
        if not eligible:
            await job.emit_complete({
                "slug": slug,
                "suggestions_written": 0,
                "edges_total": len(all_edges),
                "already_authored": already_authored,
                "skipped_no_coverage": 0,
                "image_calls": 0,
                "note": "No eligible edges (every edge already has prose).",
            })
            return

        suggestions_built: list[dict[str, Any]] = []
        skipped_no_coverage = 0
        total_image_calls = 0

        with httpx.Client(timeout=30.0) as http:
            for i, edge in enumerate(eligible):
                from_id, to_id = edge["from"], edge["to"]
                from_node = nodes_by_id.get(from_id)
                to_node = nodes_by_id.get(to_id)
                if not from_node or not to_node:
                    continue
                pct = 0.20 + 0.70 * (i / max(1, len(eligible)))
                await job.emit(
                    "processing", pct,
                    f"edge {i + 1}/{len(eligible)}: {from_id} -> {to_id}",
                )
                try:
                    suggestion = await _generate_for_edge(
                        slug=slug,
                        from_node=from_node,
                        to_node=to_node,
                        api_key=api_key,
                        interval_m=interval_m,
                        use_routing=use_routing,
                        http=http,
                    )
                except Exception as exc:  # noqa: BLE001
                    # One bad edge shouldn't kill the whole bulk run.
                    await job.emit(
                        "warning", pct,
                        scrub_secrets(
                            f"edge {from_id} -> {to_id} failed: {type(exc).__name__}: {exc}"
                        ),
                    )
                    continue
                if suggestion is None:
                    continue
                if suggestion.get("skipped_reason"):
                    skipped_no_coverage += 1
                    continue
                # We've already spent the image quota — keep the result.
                suggestions_built.append(suggestion)
                total_image_calls += len(suggestion.get("evidence", {}).get("pano_ids", []))
                if total_image_calls >= image_call_cap:
                    await job.emit(
                        "warning", pct,
                        f"image_call_cap of {image_call_cap} reached after {len(suggestions_built)} edges; "
                        "remaining edges deferred. Re-run later to fill them.",
                    )
                    break

        await job.emit("writing", 0.95, f"Writing {len(suggestions_built)} suggestions")
        sidecar = _empty_sidecar(slug)
        sidecar["suggestions"] = suggestions_built
        save_suggestions(slug, sidecar)

        await job.emit_complete({
            "slug": slug,
            "suggestions_written": len(suggestions_built),
            "edges_total": len(all_edges),
            "already_authored": already_authored,
            "skipped_no_coverage": skipped_no_coverage,
            "image_calls": total_image_calls,
            "suggestions_path": str(suggestions_path_for(slug)),
        })
    except Exception as exc:  # noqa: BLE001
        await job.emit_failed(scrub_secrets(f"{type(exc).__name__}: {exc}"))


# --- Per-edge synchronous regeneration ------------------------------------

async def regenerate_one(
    *,
    slug: str,
    from_id: str,
    to_id: str,
    interval_m: float = 20.0,
    use_routing: bool = True,
) -> dict[str, Any]:
    """Generate a fresh suggestion for one edge, upsert into the sidecar,
    and return the suggestion (including a coverage_fail entry if applicable).
    Used by the per-edge ✨ button."""
    api_key = _require_api_key()
    _facility_path, topology_path, _source = resolve_paths(slug)
    topology = read_json(topology_path)
    nodes_by_id = {n["id"]: n for n in topology.get("nodes", [])}
    from_node = nodes_by_id.get(from_id)
    to_node = nodes_by_id.get(to_id)
    if not from_node or not to_node:
        raise LookupError(f"node not found: {from_id} or {to_id}")

    suggestion = await _generate_for_edge(
        slug=slug,
        from_node=from_node,
        to_node=to_node,
        api_key=api_key,
        interval_m=interval_m,
        use_routing=use_routing,
    )
    if suggestion is None:
        raise RuntimeError("Vision call returned no suggestion.")
    upsert_suggestion(slug, suggestion)
    return suggestion
