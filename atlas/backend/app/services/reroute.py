"""
Re-route topology edges over the facility's OSM footway graph.

Used after a node drag: incident edges are rubber-banded by the editor (their
endpoint vertex moved, geometry kept and flagged stale_geometry=true). This
service rebuilds the footway graph from tools/bootstrap/<slug>/osm.json
and re-runs Dijkstra for each requested edge so curves snap back to the
sidewalks.
"""

from __future__ import annotations

from typing import Any

from app.services._io import ensure_tools_on_path, read_json, write_json_atomic
from app.services.locate import osm_path_for, resolve_paths


def reroute(
    *,
    slug: str,
    edge_indices: list[int] | None,
) -> dict[str, Any]:
    """
    Re-route either the supplied edge indices, or every edge whose
    `stale_geometry` flag is true. Returns a per-edge summary.

    Raises FileNotFoundError when the topology or osm.json is missing.
    """
    ensure_tools_on_path()
    import draft_edges_for_facility as de  # type: ignore

    _facility_path, topology_path, _source = resolve_paths(slug)
    if not topology_path.exists():
        raise FileNotFoundError(f"No topology.json for slug '{slug}'.")
    osm_path = osm_path_for(slug)
    if not osm_path.exists():
        raise FileNotFoundError(
            f"No osm.json for slug '{slug}' — re-routing needs the OSM footway "
            "layer that fetch_osm_for_facility.py produces. Try running the "
            "OSM bootstrap first."
        )

    topology = read_json(topology_path)
    osm = read_json(osm_path)
    nodes_by_id: dict[str, dict[str, Any]] = {n["id"]: n for n in topology.get("nodes", [])}
    footways: list[dict[str, Any]] = osm.get("footways") or []
    if not footways:
        raise RuntimeError(
            "osm.json has no footways — nothing to route along. Re-bootstrap "
            "with a slightly larger padding to capture surrounding paths."
        )

    vertex_pos, adj = de.build_footway_graph(footways)

    edges = topology.get("edges", [])
    if edge_indices is None:
        edge_indices = [i for i, e in enumerate(edges) if e.get("stale_geometry")]

    routed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for idx in edge_indices:
        if idx < 0 or idx >= len(edges):
            skipped.append({"index": idx, "reason": "out of range"})
            continue
        edge = edges[idx]
        a = nodes_by_id.get(edge.get("from", ""))
        b = nodes_by_id.get(edge.get("to", ""))
        if not a or not b:
            skipped.append({"index": idx, "reason": "endpoint node missing"})
            continue

        sk_a, sd_a = de.snap_to_graph(a, vertex_pos)
        sk_b, sd_b = de.snap_to_graph(b, vertex_pos)
        if not sk_a or not sk_b:
            skipped.append({"index": idx, "reason": "endpoint too far from any footway"})
            continue
        path_keys, routed_d = de.shortest_path(adj, sk_a, sk_b)
        if not path_keys:
            skipped.append({"index": idx, "reason": "no walkable path between endpoints"})
            continue

        distance = sd_a + routed_d + sd_b
        distance_m = round(distance)
        # Same walking pace as draft_edges_for_facility.
        walk_min = round(distance_m / 80 * 10) / 10
        geometry = [[a["lat"], a["lng"]]]
        geometry.extend([list(vertex_pos[k]) for k in path_keys])
        geometry.append([b["lat"], b["lng"]])
        rounded_geom = [[round(p[0], 6), round(p[1], 6)] for p in geometry]

        edge["distance_meters"] = distance_m
        edge["walk_minutes"] = walk_min
        edge["geometry"] = rounded_geom
        edge.pop("stale_geometry", None)
        routed.append({
            "index": idx,
            "from": edge.get("from"),
            "to": edge.get("to"),
            "distance_meters": distance_m,
            "walk_minutes": walk_min,
            "geometry_points": len(rounded_geom),
        })

    write_json_atomic(topology_path, topology)
    return {
        "slug": slug,
        "rerouted": routed,
        "skipped": skipped,
        "topology_path": str(topology_path),
    }
