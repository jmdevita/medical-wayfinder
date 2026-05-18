import type { Topology, TopologyEdge } from "./types";

/**
 * Dijkstra shortest path over a topology, weighted by edge.walk_minutes.
 * Treats edges as bidirectional. Returns the ordered list of edges along
 * the path (each annotated with the direction the patient walks them).
 *
 * This mirrors the orchestrator's route resolver in the Flutter app, kept
 * close enough that the Preview pane shows the same path the on-device
 * model would receive in its context block.
 */
export interface RouteEdge extends TopologyEdge {
  /** Node id the patient is leaving */
  origin: string;
  /** Node id the patient is arriving at */
  arrival: string;
}

export interface RouteResult {
  fromId: string;
  toId: string;
  edges: RouteEdge[];
  totalDistanceM: number;
  totalWalkMin: number;
}

export interface RouteOptions {
  /** When true, edges tagged with `stairs` are excluded from the graph. */
  accessibility?: boolean;
}

export function findRoute(
  topology: Topology,
  fromId: string,
  toId: string,
  opts: RouteOptions = {},
): RouteResult | null {
  if (fromId === toId) {
    return { fromId, toId, edges: [], totalDistanceM: 0, totalWalkMin: 0 };
  }
  const adj = new Map<string, { edge: TopologyEdge; other: string }[]>();
  for (const e of topology.edges) {
    if (e.blocked) continue;
    if (opts.accessibility && e.accessibility_features?.includes("stairs")) continue;
    if (!adj.has(e.from)) adj.set(e.from, []);
    if (!adj.has(e.to))   adj.set(e.to, []);
    adj.get(e.from)!.push({ edge: e, other: e.to });
    adj.get(e.to)!.push({ edge: e, other: e.from });
  }
  if (!adj.has(fromId) || !adj.has(toId)) return null;

  const dist = new Map<string, number>();
  const prev = new Map<string, { from: string; edge: TopologyEdge }>();
  for (const id of adj.keys()) dist.set(id, Infinity);
  dist.set(fromId, 0);

  // Naive priority queue is fine for tens of nodes per facility.
  const visited = new Set<string>();
  while (visited.size < adj.size) {
    let cur: string | null = null;
    let curDist = Infinity;
    for (const [id, d] of dist) {
      if (!visited.has(id) && d < curDist) {
        cur = id;
        curDist = d;
      }
    }
    if (cur === null || curDist === Infinity) break;
    if (cur === toId) break;
    visited.add(cur);

    for (const { edge, other } of adj.get(cur) ?? []) {
      const alt = curDist + (edge.walk_minutes || 0);
      if (alt < (dist.get(other) ?? Infinity)) {
        dist.set(other, alt);
        prev.set(other, { from: cur, edge });
      }
    }
  }

  if (!prev.has(toId) && fromId !== toId) return null;

  // Reconstruct.
  const reversed: RouteEdge[] = [];
  let cursor = toId;
  while (cursor !== fromId) {
    const step = prev.get(cursor);
    if (!step) return null;
    reversed.push({ ...step.edge, origin: step.from, arrival: cursor });
    cursor = step.from;
  }
  const edges = reversed.reverse();
  return {
    fromId,
    toId,
    edges,
    totalDistanceM: edges.reduce((s, e) => s + (e.distance_meters || 0), 0),
    totalWalkMin: edges.reduce((s, e) => s + (e.walk_minutes || 0), 0),
  };
}
