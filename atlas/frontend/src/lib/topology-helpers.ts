import type { TopologyNode } from "./types";

const EARTH_RADIUS_M = 6371000;

/** Haversine great-circle distance in meters between two lat/lng pairs. */
export function haversineMeters(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const sa =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(sa), Math.sqrt(1 - sa));
  return Math.round(EARTH_RADIUS_M * c);
}

/** Walking pace ~80 m/min — matches the orchestrator's assumption. */
export function walkMinutes(distanceM: number): number {
  return Math.round((distanceM / 80) * 10) / 10;
}

/** Total meters along a polyline of [lat, lng] vertices. */
export function polylineMeters(latlngs: Array<[number, number]>): number {
  let total = 0;
  for (let i = 1; i < latlngs.length; i++) {
    const a = { lat: latlngs[i - 1][0], lng: latlngs[i - 1][1] };
    const b = { lat: latlngs[i][0], lng: latlngs[i][1] };
    total += haversineMeters(a, b);
  }
  return total;
}

/** Pick the first id of the form `<prefix>_<n>` that no existing node uses. */
export function uniqueNodeId(existing: TopologyNode[], prefix = "node"): string {
  const taken = new Set(existing.map((n) => n.id));
  let n = 1;
  while (taken.has(`${prefix}_${n}`)) n++;
  return `${prefix}_${n}`;
}
