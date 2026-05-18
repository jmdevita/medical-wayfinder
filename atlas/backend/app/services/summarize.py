"""
Helpers that turn a full facility/topology pair into the lightweight summary
the dashboard's Facilities grid needs. Kept separate from the route so it can
be reused by the publish endpoint and unit-tested in isolation.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

# Region inference. The facility JSON's address ends in a US state code; we
# group multiple states into broader regions for the dashboard filter chips.
_REGION_BY_STATE: dict[str, str] = {
    "MA": "Boston",
    "NH": "Boston",
    "RI": "Boston",
    "CT": "Boston",
    "ME": "Boston",
    "VT": "Boston",
    "CA": "Los Angeles",
    "NV": "Los Angeles",
    "AZ": "Los Angeles",
}


def infer_region(address: str) -> str:
    """Best-effort region from the address tail. Returns 'Other' if no match."""
    if not address:
        return "Other"
    # Pick out the last whitespace-separated token before any zip; common form
    # is "City, ST 12345" or "City, ST".
    parts = [p.strip() for p in address.split(",")]
    if not parts:
        return "Other"
    tail = parts[-1].strip()
    # tail might be "MA 02130" or "MA"
    state_token = tail.split()[0] if tail else ""
    return _REGION_BY_STATE.get(state_token.upper(), "Other")


def humanize_age(mtime: float) -> str:
    """Render an mtime as a relative phrase (e.g. '3 hours ago')."""
    delta = dt.datetime.now() - dt.datetime.fromtimestamp(mtime)
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    months = days // 30
    return f"{months} month{'s' if months != 1 else ''} ago"


def status_for(source: str, edges: list[Any]) -> str:
    """
    Status hint based on where the file lives and whether topology has edges.
    A published facility with no edges drops back to 'review' so the grid
    flags it for attention.
    """
    if source == "published":
        return "published" if edges else "review"
    return "draft" if edges else "bootstrap"


def build_mini_map(
    *,
    lat: float,
    lng: float,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    sample_limit: int = 12,
) -> dict[str, Any]:
    """
    Project topology nodes into the card's 0–100 / 0–60 viewBox. We compute
    the lat/lng bounding box, scale into the viewBox with 8% padding, and
    optionally sample down to keep the thumbnail readable.
    """
    if not nodes:
        return {"lat": lat, "lng": lng, "nodes": [], "edges": []}

    lats = [n["lat"] for n in nodes]
    lngs = [n["lng"] for n in nodes]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    # Avoid divide-by-zero on a single-node topology.
    span_lat = max(max_lat - min_lat, 1e-6)
    span_lng = max(max_lng - min_lng, 1e-6)

    pad_x, pad_y = 8.0, 6.0
    w, h = 100.0 - 2 * pad_x, 60.0 - 2 * pad_y

    def project(n: dict[str, Any]) -> tuple[float, float]:
        # Lng goes left-to-right, lat goes bottom-to-top (so flip y).
        x = pad_x + ((n["lng"] - min_lng) / span_lng) * w
        y = pad_y + (1.0 - (n["lat"] - min_lat) / span_lat) * h
        return round(x, 2), round(y, 2)

    # Index nodes by id for edge resolution before any sampling.
    projected: dict[str, dict[str, Any]] = {}
    for n in nodes:
        x, y = project(n)
        projected[n["id"]] = {"x": x, "y": y, "t": n.get("type", "junction")}

    # Sample for visual clarity. Prefer entrances and parking; drop floor/junction first.
    priority = {"entrance": 0, "parking": 1, "transit": 2, "landmark": 3, "junction": 4, "floor": 5}
    if len(nodes) > sample_limit:
        sorted_nodes = sorted(nodes, key=lambda n: priority.get(n.get("type", "junction"), 9))
        kept_ids = {n["id"] for n in sorted_nodes[:sample_limit]}
    else:
        kept_ids = set(projected.keys())

    out_nodes_list = [n for n in nodes if n["id"] in kept_ids]
    id_to_index = {n["id"]: i for i, n in enumerate(out_nodes_list)}
    out_nodes = [projected[n["id"]] for n in out_nodes_list]
    out_edges = [
        [id_to_index[e["from"]], id_to_index[e["to"]]]
        for e in edges
        if e.get("from") in id_to_index and e.get("to") in id_to_index
    ]

    return {"lat": lat, "lng": lng, "nodes": out_nodes, "edges": out_edges}


def centroid(buildings: list[dict[str, Any]] | None, fallback: tuple[float, float]) -> tuple[float, float]:
    """Average the building lat/lngs; fall back to a hardcoded pair if empty."""
    if not buildings:
        return fallback
    pts = [(b["lat"], b["lng"]) for b in buildings if "lat" in b and "lng" in b]
    if not pts:
        return fallback
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def file_signature(p: Path) -> tuple[float, str]:
    """Return (mtime, owner) — owner is 'you' for now since we don't track auth."""
    stat = p.stat()
    return stat.st_mtime, "you"
