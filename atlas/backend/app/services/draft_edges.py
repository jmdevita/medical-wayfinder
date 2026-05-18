"""
Async wrapper around `tools/draft_edges_for_facility.py`.

Auto-routes edges between entrance/parking/transit/landmark nodes using the
facility's OSM footway graph (or straight-line as fallback). Adds new edges
to topology.json with a TODO-stub instruction string for humans to refine.

This is fast (no LLM call). Wrapped as a job for symmetry and so the UI gets
the same progress shape as the slower LLM-driven jobs.
"""

from __future__ import annotations

import asyncio

from app.jobs import Job
from app.services._io import ensure_tools_on_path, read_json, write_json_atomic
from app.services.locate import osm_path_for, resolve_paths


async def run_draft_edges(
    job: Job,
    *,
    slug: str,
    max_dist: int = 800,
) -> None:
    try:
        await job.emit("starting", 0.05, f"Drafting edges for '{slug}' (max {max_dist}m)")
        ensure_tools_on_path()
        import draft_edges_for_facility as de  # type: ignore

        _facility_path, topology_path, _source = resolve_paths(slug)
        if not topology_path.exists():
            raise FileNotFoundError(f"No topology.json for slug '{slug}'.")
        topology = read_json(topology_path)
        nodes = topology.get("nodes", [])
        existing = {(e["from"], e["to"]) for e in topology.get("edges", [])}

        await job.emit("loading_osm", 0.20, "Loading OSM reference layer…")
        osm_path = osm_path_for(slug)
        footways: list[dict] = []
        if osm_path.exists():
            footways = (read_json(osm_path).get("footways") or [])
        if not footways:
            await job.emit("warning", 0.25, "No footways available — drafts will be straight-line.")

        await job.emit("graph", 0.35, f"Building footway graph ({len(footways)} segments)")
        vertex_pos, adj = await asyncio.to_thread(de.build_footway_graph, footways)

        await job.emit("routing", 0.55, f"Routing pairs over {len(vertex_pos)} vertices…")
        drafts = await asyncio.to_thread(
            de.draft_edges, nodes, vertex_pos, adj, existing, max_dist,
        )

        if not drafts:
            await job.emit_complete({
                "slug": slug,
                "edges_drafted": 0,
                "edges_total": len(topology.get("edges", [])),
                "topology_path": str(topology_path),
                "note": "No new edges fit the budget. Existing edges preserved.",
            })
            return

        await job.emit("merging", 0.92, f"Merging {len(drafts)} new edges")
        topology["edges"] = list(topology.get("edges", [])) + drafts
        write_json_atomic(topology_path, topology)

        await job.emit_complete({
            "slug": slug,
            "edges_drafted": len(drafts),
            "edges_total": len(topology["edges"]),
            "topology_path": str(topology_path),
        })
    except Exception as exc:  # noqa: BLE001
        await job.emit_failed(f"{type(exc).__name__}: {exc}")
