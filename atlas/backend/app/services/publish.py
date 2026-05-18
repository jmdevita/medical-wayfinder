"""
Pre-publish validation. Surfaces every reason a facility can't ship in one
response, so the editor can show a checklist instead of fixing one error,
saving, retrying, fixing the next, etc.

`validate_facility` returns *blocking* issues — publish refuses unless
force=True. `compute_warnings` returns non-blocking quality flags (e.g.
sparse department mapping) that the UI surfaces to the author but doesn't
gate publish on.
"""

from __future__ import annotations

from typing import Any

# Warn when fewer than this fraction of departments are pinned to a topology
# node. Below the threshold, on-device wayfinding can only fall back to the
# building/floor blurb for too many departments.
DEPT_MAPPING_WARN_THRESHOLD = 0.75


def validate_facility(facility: dict[str, Any], topology: dict[str, Any] | None) -> list[str]:
    """Return a list of human-readable reasons this facility shouldn't publish.
    Empty list = clean."""
    issues: list[str] = []

    name = facility.get("name")
    if not isinstance(name, str) or not name.strip():
        issues.append("facility.json is missing a non-empty 'name'")

    if not isinstance(facility.get("address"), str) or not facility["address"].strip():
        issues.append("facility.json is missing 'address'")

    buildings = facility.get("buildings") or []
    if not buildings:
        issues.append("facility.json must declare at least one building")

    departments = facility.get("departments") or []
    if not departments:
        issues.append("facility.json has no departments")

    if topology is None:
        issues.append("topology.json is missing")
        return issues

    nodes = topology.get("nodes") or []
    edges = topology.get("edges") or []
    if not nodes:
        issues.append("topology.json has no nodes")

    node_ids = {n.get("id") for n in nodes if isinstance(n.get("id"), str)}
    for i, e in enumerate(edges):
        if e.get("from") not in node_ids:
            issues.append(f"topology edge {i} references unknown 'from' node: {e.get('from')!r}")
        if e.get("to") not in node_ids:
            issues.append(f"topology edge {i} references unknown 'to' node: {e.get('to')!r}")

    todo_edges = [
        i for i, e in enumerate(edges)
        if isinstance(e.get("instruction"), str) and "TODO" in e["instruction"]
    ]
    if todo_edges:
        issues.append(
            f"{len(todo_edges)} edge(s) still carry TODO-stub instructions "
            "(run /draft-edges or author them in the editor)"
        )

    empty_instr = [
        i for i, e in enumerate(edges)
        if not (e.get("instruction") or "").strip()
    ]
    if empty_instr:
        issues.append(f"{len(empty_instr)} edge(s) have empty instructions")

    # Cross-check: every department.topology_node_id (if set) references a real node.
    for d in departments:
        nid = d.get("topology_node_id")
        if nid and nid not in node_ids:
            issues.append(
                f"department {d.get('name', '?')!r} pins missing node: {nid!r}"
            )

    return issues


def compute_warnings(facility: dict[str, Any], topology: dict[str, Any] | None) -> list[str]:
    """Non-blocking quality checks. Empty list = nothing notable."""
    warnings: list[str] = []

    departments = facility.get("departments") or []
    if departments and topology is not None:
        node_ids = {n.get("id") for n in (topology.get("nodes") or []) if isinstance(n.get("id"), str)}
        # Count departments whose topology_node_id is set AND points to a real
        # node — stale pins (caught as issues elsewhere) don't count as mapped.
        mapped = sum(
            1 for d in departments
            if d.get("topology_node_id") and d.get("topology_node_id") in node_ids
        )
        total = len(departments)
        ratio = mapped / total if total else 0.0
        if ratio < DEPT_MAPPING_WARN_THRESHOLD:
            pct = round(ratio * 100)
            target_pct = round(DEPT_MAPPING_WARN_THRESHOLD * 100)
            warnings.append(
                f"Only {mapped}/{total} departments ({pct}%) are pinned to a topology node "
                f"— aim for ≥{target_pct}% so patients get turn-by-turn directions instead of just a building/floor blurb."
            )

    return warnings
