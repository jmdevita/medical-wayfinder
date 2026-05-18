/**
 * Shapes that mirror the Flutter app's facility + topology JSON.
 * Source of truth: `health_wayfinder/lib/models/facility.dart` and
 * `lib/models/topology.dart`. Keep this file in sync.
 */

export type NodeType =
  | "parking"
  | "entrance"
  | "landmark"
  | "junction"
  | "transit"
  | "floor";

export interface TopologyNode {
  id: string;
  type: NodeType;
  label: string;
  description: string;
  keywords: string[];
  lat: number;
  lng: number;
}

export type AccessibilityFeature =
  | "elevator"
  | "ramp"
  | "automatic_doors"
  | "accessible_entrance"
  | "stairs";

export interface TopologyEdge {
  from: string;
  to: string;
  distance_meters: number;
  walk_minutes: number;
  instruction: string;
  blocked: boolean;
  geometry?: [number, number][];
  /**
   * True when an endpoint moved and the routed footway geometry is no longer
   * accurate — only the first/last vertex was rebased to the new position.
   * The /reroute-edges endpoint clears this when it re-routes.
   */
  stale_geometry?: boolean;
  /**
   * Structured accessibility tags. `stairs` marks an edge as not wheelchair-
   * passable; the others are positive affordances surfaced as step badges.
   */
  accessibility_features?: AccessibilityFeature[];
}

export interface Topology {
  version: string;
  facility_id: string;
  name: string;
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export interface Department {
  name: string;
  building: string;
  floor?: string;
  topology_node_id?: string;
  aliases?: string[];
  hours?: string;
  check_in?: string;
  accessible?: boolean;
}

export type FacilityStatus = "published" | "review" | "draft" | "bootstrap";

export interface FacilityMeta {
  id: string;
  name: string;
  region: string;
  address: string;
  type: string;
  nodes: number;
  edges: number;
  depts: number;
  issues: number;
  status: FacilityStatus;
  updated: string;
  by: string;
  miniMap: {
    lat: number;
    lng: number;
    nodes: { x: number; y: number; t: NodeType }[];
    edges: [number, number][];
  };
}

