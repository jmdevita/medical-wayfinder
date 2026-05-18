"""
Async wrapper around `tools/fetch_osm_for_facility.py`.

The existing CLI pipeline geocodes via Nominatim, queries Overpass, filters,
and emits three JSON files. We re-use its helpers (geocode, overpass_query,
is_relevant, build_*_bootstrap) and write into the same `tools/bootstrap/`
workspace the CLI uses — atlas just adds Job progress events on top.

The CLI's helpers are synchronous and use urllib. We push them into a worker
thread via `asyncio.to_thread()` so the event loop stays responsive while the
HTTP calls block.
"""

from __future__ import annotations

import asyncio
import re

from app.jobs import Job
from app.paths import BOOTSTRAP_DIR
from app.services._io import ensure_tools_on_path, write_json_atomic

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def slugify(text: str) -> str:
    s = _SLUG_RE.sub("_", text.lower()).strip("_")
    return s or "facility"


async def run_bootstrap(job: Job, slug: str, query: str, include_landmarks: bool = False) -> None:
    """
    Drive the full bootstrap pipeline, emitting progress events along the way.
    On success, writes osm.json + facility.json + topology.json under
    tools/bootstrap/<slug>/ and stamps the job result with their paths.
    """
    try:
        await job.emit("starting", 0.02, f"Bootstrapping '{slug}' from query: {query!r}")
        ensure_tools_on_path()
        # Imported here so the path manipulation above takes effect first.
        import fetch_osm_for_facility as osm  # type: ignore

        await job.emit("geocoding", 0.10, "Geocoding via Nominatim…")
        geo = await asyncio.to_thread(osm.geocode, query)
        await job.emit(
            "geocoded",
            0.20,
            f"Found: {geo.get('display_name', 'unknown')[:80]}",
        )

        # Polite pause for Nominatim before hitting Overpass.
        await asyncio.sleep(1.0)

        await job.emit("overpass", 0.30, "Querying OpenStreetMap (Overpass)…")
        elements = await asyncio.to_thread(osm.overpass_query, geo["bbox"])
        await job.emit("overpass_done", 0.55, f"{len(elements)} raw elements")

        await job.emit("filtering", 0.65, "Filtering residential noise…")
        features = [el for el in elements if osm.is_relevant(el, include_landmarks)]
        if not features:
            raise RuntimeError(
                "No relevant features found. Try a more specific query or "
                "increase the bounding box."
            )
        await job.emit("filtered", 0.75, f"{len(features)} relevant features")

        await job.emit("building_layers", 0.82, "Building OSM reference layer…")
        osm_layer = await asyncio.to_thread(osm.build_reference_layer, features, slug)

        await job.emit("building_facility", 0.88, "Building facility.json…")
        facility = await asyncio.to_thread(osm.build_facility_bootstrap, slug, geo, features)

        await job.emit("building_topology", 0.93, "Seeding topology nodes…")
        topology = await asyncio.to_thread(
            osm.build_topology_bootstrap, slug, geo, features, include_landmarks
        )

        await job.emit("writing", 0.97, "Writing files…")
        out_dir = BOOTSTRAP_DIR / slug
        write_json_atomic(out_dir / "osm.json", osm_layer)
        write_json_atomic(out_dir / "facility.json", facility)
        write_json_atomic(out_dir / "topology.json", topology)

        await job.emit_complete({
            "slug": slug,
            "out_dir": str(out_dir),
            "buildings": len(facility.get("buildings", [])),
            "parking": len(facility.get("parking", [])),
            "topology_nodes": len(topology.get("nodes", [])),
            "osm_features": len(osm_layer.get("features", [])),
        })
    except Exception as exc:  # noqa: BLE001 — we want anything bubbled into the SSE stream.
        await job.emit_failed(f"{type(exc).__name__}: {exc}")
