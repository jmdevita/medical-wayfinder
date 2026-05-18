#!/usr/bin/env python3
"""
Draft topology edges for a facility by routing along OSM footways.

Reads:
  tools/bootstrap/<slug>/topology.json   (nodes from fetch_osm_for_facility.py)
  tools/bootstrap/<slug>/osm.json        (footways from same)

For each entrance node, drafts edges to every nearby parking/landmark/transit
node + every other entrance, routed along the actual sidewalk graph instead
of straight lines. Each edge gets a `geometry` polyline so the editor can
render the real walking path.

Existing human-authored edges are preserved (matched by from->to pair).
Re-running the tool only adds missing edges; it never overwrites.

If no footways are available (rural / poorly mapped area), falls back to
straight-line haversine edges with a warning.

Usage:
  env/bin/python tools/draft_edges_for_facility.py <slug> [--write] [--max-dist M]

Without --write: prints proposed edges to stdout for inspection.
With --write:    merges into tools/bootstrap/<slug>/topology.json.

Tunable:
  --max-dist N    Cap routed distance per edge (meters, default 800). Edges
                  longer than this are dropped — too far to be a useful
                  walking instruction.
"""

import argparse
import heapq
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"


# ---- Geometry helpers ------------------------------------------------------

R_EARTH = 6371000


def hav(a: tuple, b: tuple) -> float:
    """Haversine distance in meters between (lat,lng) pairs."""
    lat1, lng1 = a
    lat2, lng2 = b
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    x = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return 2 * R_EARTH * math.atan2(math.sqrt(x), math.sqrt(1 - x))


def quantize(p: tuple, snap_m: float = 3.0) -> tuple:
    """Round (lat,lng) to a precision approximating `snap_m` meters so that
    near-coincident footway endpoints collapse to a single graph vertex."""
    # 1 deg lat ~= 111_000 m; pick precision matching snap_m.
    digits = max(0, int(round(math.log10(111_000 / snap_m))))
    return (round(p[0], digits), round(p[1], digits))


# ---- Footway graph ---------------------------------------------------------

def build_footway_graph(footways: list[dict]) -> tuple[dict, dict]:
    """Return (vertex_pos, adjacency).

    vertex_pos: quantized_key -> exact (lat,lng) of one of the merged points.
    adjacency: quantized_key -> list of (neighbor_key, distance_m).
    """
    vertex_pos: dict = {}
    adj: dict = {}

    for fw in footways:
        path = fw.get("path", [])
        prev_key = None
        for raw in path:
            pt = (raw[0], raw[1])
            key = quantize(pt)
            if key not in vertex_pos:
                vertex_pos[key] = pt
                adj[key] = []
            if prev_key is not None and prev_key != key:
                d = hav(vertex_pos[prev_key], vertex_pos[key])
                adj[prev_key].append((key, d))
                adj[key].append((prev_key, d))
            prev_key = key
    return vertex_pos, adj


def snap_to_graph(node: dict, vertex_pos: dict, max_snap_m: float = 60.0):
    """Find the nearest footway vertex to a topology node. Returns (key, dist)
    or (None, inf) if no vertex is within max_snap_m."""
    best, best_d = None, float("inf")
    target = (node["lat"], node["lng"])
    for k, pos in vertex_pos.items():
        d = hav(target, pos)
        if d < best_d:
            best, best_d = k, d
    if best_d > max_snap_m:
        return None, float("inf")
    return best, best_d


def shortest_path(adj: dict, start, end) -> tuple[list, float]:
    """Dijkstra. Returns (path_keys, total_distance) or ([], inf) if no path."""
    if start == end:
        return [start], 0.0
    pq = [(0.0, start)]
    dist = {start: 0.0}
    prev = {}
    while pq:
        d, u = heapq.heappop(pq)
        if u == end:
            path = [u]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            path.reverse()
            return path, d
        if d > dist[u]:
            continue
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return [], float("inf")


# ---- Edge drafting ---------------------------------------------------------

# Per-pair distance budget. Beyond this, the edge is dropped — not a useful
# patient walk. Per type combination, in meters.
MAX_DIST_BY_TYPE = {
    ("entrance", "parking"):   600,
    ("entrance", "landmark"):  400,
    ("entrance", "transit"):   800,
    ("entrance", "entrance"): 1000,
}


def edge_budget(t1: str, t2: str, default: int) -> int:
    pair = tuple(sorted([t1, t2]))
    # Normalize to (entrance, X) shape if entrance present
    if "entrance" in pair:
        other = next(t for t in pair if t != "entrance") if pair[0] != pair[1] else "entrance"
        return MAX_DIST_BY_TYPE.get(("entrance", other), default)
    return default


def draft_edges(nodes: list[dict],
                vertex_pos: dict, adj: dict,
                existing: set[tuple],
                default_max_dist: int) -> list[dict]:
    """Generate edges from each entrance to nearby parking/landmark/transit/
    other-entrance nodes, routed via footways."""
    drafts = []
    by_type = {"entrance": [], "parking": [], "landmark": [], "transit": []}
    for n in nodes:
        if n["type"] in by_type:
            by_type[n["type"]].append(n)

    if not by_type["entrance"]:
        print("  WARNING: no entrance nodes; nothing to draft.", file=sys.stderr)
        return []

    # Pre-snap every node once.
    snaps = {}
    for n in nodes:
        if n["type"] in by_type:
            snaps[n["id"]] = snap_to_graph(n, vertex_pos) if vertex_pos else (None, float("inf"))

    pair_seen = set()  # avoid double-emitting entrance<->entrance pairs
    for ent in by_type["entrance"]:
        targets = (
            by_type["parking"] + by_type["landmark"]
            + by_type["transit"] + by_type["entrance"]
        )
        for tgt in targets:
            if tgt["id"] == ent["id"]:
                continue
            pair = tuple(sorted([ent["id"], tgt["id"]]))
            if pair in pair_seen:
                continue
            pair_seen.add(pair)
            if (ent["id"], tgt["id"]) in existing or (tgt["id"], ent["id"]) in existing:
                continue

            budget = edge_budget(ent["type"], tgt["type"], default_max_dist)

            # Try footway routing first; fall back to straight-line.
            geometry = None
            distance = float("inf")
            sk_ent, sd_ent = snaps[ent["id"]]
            sk_tgt, sd_tgt = snaps[tgt["id"]]
            if sk_ent and sk_tgt:
                path_keys, routed_d = shortest_path(adj, sk_ent, sk_tgt)
                if path_keys:
                    distance = sd_ent + routed_d + sd_tgt
                    geometry = (
                        [[ent["lat"], ent["lng"]]]
                        + [list(vertex_pos[k]) for k in path_keys]
                        + [[tgt["lat"], tgt["lng"]]]
                    )
            if distance == float("inf"):
                distance = hav((ent["lat"], ent["lng"]),
                               (tgt["lat"], tgt["lng"]))
                geometry = None  # editor draws straight line

            if distance > budget:
                continue

            distance_m = round(distance)
            walk = round(distance_m / 80 * 10) / 10
            stub = (f"TODO: describe walking from {ent['label']} "
                    f"to {tgt['label']}.")

            edge = {
                "from": ent["id"],
                "to": tgt["id"],
                "distance_meters": distance_m,
                "walk_minutes": walk,
                "instruction": stub,
                "blocked": False,
            }
            if geometry:
                # Round polyline points for size.
                edge["geometry"] = [[round(p[0], 6), round(p[1], 6)]
                                     for p in geometry]
            drafts.append(edge)
    return drafts


# ---- Main ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Draft topology edges via OSM footway routing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("slug", help="Facility slug (matches tools/bootstrap/<slug>/)")
    ap.add_argument("--write", action="store_true",
                    help="Merge drafts into topology.json (preserves existing edges).")
    ap.add_argument("--max-dist", type=int, default=800,
                    help="Default per-edge distance cap in meters (default 800).")
    args = ap.parse_args()

    boot = TOOLS_DIR / "bootstrap" / args.slug
    topo_path = boot / "topology.json"
    osm_path = boot / "osm.json"
    if not topo_path.exists():
        raise SystemExit(f"Missing {topo_path.relative_to(ROOT)}")

    topo = json.loads(topo_path.read_text())
    nodes = topo.get("nodes", [])
    existing = {(e["from"], e["to"]) for e in topo.get("edges", [])}

    footways = []
    if osm_path.exists():
        osm = json.loads(osm_path.read_text())
        footways = osm.get("footways", []) or []
    if not footways:
        print(f"  WARNING: no footways in osm.json — drafts will be straight-line.",
              file=sys.stderr)

    vertex_pos, adj = build_footway_graph(footways)
    print(f"Footway graph: {len(vertex_pos)} vertices, "
          f"{sum(len(v) for v in adj.values()) // 2} edges", file=sys.stderr)

    drafts = draft_edges(nodes, vertex_pos, adj, existing,
                         default_max_dist=args.max_dist)

    print(f"\nDrafted {len(drafts)} edges "
          f"({len(existing)} existing preserved):", file=sys.stderr)
    by_id = {n["id"]: n for n in nodes}
    for e in drafts:
        f = by_id.get(e["from"], {}).get("label", e["from"])[:30]
        t = by_id.get(e["to"], {}).get("label", e["to"])[:30]
        geo_marker = "via footways" if "geometry" in e else "STRAIGHT-LINE"
        print(f"  {f:30} -> {t:30} {e['distance_meters']:>4}m "
              f"{e['walk_minutes']:>4} min  ({geo_marker})", file=sys.stderr)

    if args.write:
        topo["edges"] = list(topo.get("edges", [])) + drafts
        topo_path.write_text(json.dumps(topo, indent=2, ensure_ascii=False) + "\n")
        print(f"\nWrote {len(drafts)} new edges into {topo_path.relative_to(ROOT)}",
              file=sys.stderr)
    else:
        print(json.dumps(drafts, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
