#!/usr/bin/env python3
"""
Generate a self-contained HTML page that visualizes every facility's
topology overlaid on an OpenStreetMap basemap.

Reads:
  health_wayfinder/assets/facilities/<facility>.json
  health_wayfinder/assets/facilities/<facility>.topology.json

Writes:
  tools/topology_viewer.html

Run from repo root:
  python tools/build_topology_viewer.py
  open tools/topology_viewer.html

The output embeds all JSON data so it works as a file:// open — no
server needed. Re-run after editing any topology JSON to refresh.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACILITY_DIR = ROOT / "health_wayfinder" / "assets" / "facilities"
OUT = ROOT / "tools" / "topology_viewer.html"


def load_facilities():
    facilities = []
    tools_dir = ROOT / "tools"
    for fac_path in sorted(FACILITY_DIR.glob("*.json")):
        if fac_path.name.endswith(".topology.json"):
            continue
        topo_path = FACILITY_DIR / f"{fac_path.stem}.topology.json"
        if not topo_path.exists():
            continue
        # Optional OSM reference layer — building footprints from OSM that we
        # pulled offline. Lets the viewer show real building outlines under
        # the topology nodes.
        # OSM reference layer lives in tools/bootstrap/<slug>/osm.json. Older
        # layouts dropped it directly under tools/, so fall back for back-compat.
        osm_path = tools_dir / "bootstrap" / fac_path.stem / "osm.json"
        if not osm_path.exists():
            osm_path = tools_dir / f"{fac_path.stem}.osm.json"
        osm = json.loads(osm_path.read_text()) if osm_path.exists() else None
        facilities.append({
            "stem": fac_path.stem,
            "facility": json.loads(fac_path.read_text()),
            "topology": json.loads(topo_path.read_text()),
            "osm": osm,
        })
    return facilities


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Health Wayfinder — Topology Viewer</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body { margin: 0; padding: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  #app { display: flex; flex-direction: column; height: 100vh; }
  header {
    padding: 12px 18px; background: #1f2937; color: #fff;
    display: flex; align-items: center; gap: 16px;
  }
  header h1 { font-size: 16px; margin: 0; font-weight: 600; }
  header select { padding: 6px 10px; border-radius: 6px; border: 1px solid #374151; background: #111827; color: #fff; font-size: 14px; }
  header label.toggle { font-size: 13px; color: #d1d5db; cursor: pointer; user-select: none; display: inline-flex; align-items: center; gap: 6px; }
  header .stats { font-size: 12px; color: #9ca3af; margin-left: auto; }
  #map { flex: 1; }
  .legend {
    background: rgba(255,255,255,0.95); padding: 10px 14px; border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15); font-size: 12px; line-height: 1.6;
  }
  .legend strong { display: block; margin-bottom: 4px; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.05em; color: #374151; }
  .legend .swatch { display: inline-block; width: 12px; height: 12px;
    border-radius: 50%; margin-right: 6px; vertical-align: middle;
    border: 2px solid rgba(0,0,0,0.2); }
  .popup-content { font-size: 13px; max-width: 280px; }
  .popup-content .id { color: #6b7280; font-family: ui-monospace, monospace; font-size: 11px; }
  .popup-content .label { font-weight: 700; margin: 2px 0 6px; }
  .popup-content .desc { color: #374151; margin-bottom: 6px; }
  .popup-content .kw { color: #6b7280; font-size: 11px; font-style: italic; }
  .popup-content .meta { color: #6b7280; font-size: 11px; margin-top: 4px; }
  .popup-content .depts { margin: 8px 0; padding: 8px; background: #f9fafb; border-radius: 6px; }
  .popup-content .depts-header { font-weight: 700; font-size: 11px; color: #374151; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
  .popup-content .depts ul { margin: 0; padding-left: 18px; }
  .popup-content .depts li { margin: 3px 0; }
  .popup-content .floor { color: #6b7280; font-weight: 400; font-size: 11px; }
  .leaflet-tooltip.node-label {
    background: rgba(255,255,255,0.92); border: 1px solid #d1d5db;
    border-radius: 4px; padding: 1px 6px; font-size: 11px; font-weight: 600;
    color: #1f2937; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>Topology Viewer</h1>
    <select id="facility"></select>
    <label class="toggle"><input type="checkbox" id="showOsm" checked> Show OSM building outlines</label>
    <span class="stats" id="stats"></span>
  </header>
  <div id="map"></div>
</div>

<script>
const FACILITIES = __FACILITIES_JSON__;

const TYPE_COLORS = {
  parking:  "#2563eb",  // blue
  entrance: "#dc2626",  // red
  landmark: "#ea580c",  // orange
  junction: "#6b7280",  // gray
  transit:  "#7c3aed",  // purple
  floor:    "#9ca3af",  // light gray
};

const TYPE_RADIUS = {
  parking: 9, entrance: 9, landmark: 7, junction: 6, transit: 8, floor: 5,
};

const map = L.map('map', { zoomControl: true });
// CartoDB Voyager tiles — free, no API key, no Referer requirement (so
// file:// opens work). OSM's own tile server blocks no-referer requests.
L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
  maxZoom: 20,
  subdomains: 'abcd',
  attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
}).addTo(map);

const layerGroup = L.layerGroup().addTo(map);
const osmLayer = L.layerGroup().addTo(map);

const legend = L.control({ position: 'bottomright' });
legend.onAdd = () => {
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML = '<strong>Node types</strong>' +
    Object.entries(TYPE_COLORS).map(([t, c]) =>
      `<div><span class="swatch" style="background:${c}"></span>${t}</div>`
    ).join('');
  return div;
};
legend.addTo(map);

const select = document.getElementById('facility');
FACILITIES.forEach((f, i) => {
  const opt = document.createElement('option');
  opt.value = i;
  opt.textContent = f.facility.name;
  select.appendChild(opt);
});

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}

function renderFacility(idx) {
  layerGroup.clearLayers();
  osmLayer.clearLayers();
  const f = FACILITIES[idx];
  const nodes = f.topology.nodes;
  const edges = f.topology.edges;

  document.getElementById('stats').textContent =
    `${nodes.length} nodes · ${edges.length} edges${f.osm ? ` · ${f.osm.features.length} OSM features` : ''}`;

  // OSM reference layer — real building footprints from OpenStreetMap.
  if (f.osm) {
    f.osm.features.forEach(feat => {
      const isParking = feat.amenity === 'parking' || feat.building === 'parking';
      const isHospital = feat.building === 'hospital';
      const poly = L.polygon(feat.polygon, {
        color: isParking ? '#3b82f6' : (isHospital ? '#ef4444' : '#9ca3af'),
        weight: 1.5,
        fillColor: isParking ? '#bfdbfe' : (isHospital ? '#fecaca' : '#e5e7eb'),
        fillOpacity: 0.4,
        interactive: true,
      });
      if (feat.name) {
        poly.bindTooltip(feat.name, {
          permanent: false, direction: 'center', className: 'node-label'
        });
      }
      poly.bindPopup(`
        <div class="popup-content">
          <div class="id">OSM · ${escapeHtml(feat.building || feat.amenity || '?')}</div>
          <div class="label">${escapeHtml(feat.name || '(unnamed)')}</div>
          <div class="meta">From OpenStreetMap</div>
        </div>
      `);
      poly.addTo(osmLayer);
    });
  }

  const nodeById = Object.fromEntries(nodes.map(n => [n.id, n]));
  const points = [];

  // Edges first so markers render on top.
  edges.forEach(e => {
    const a = nodeById[e.from], b = nodeById[e.to];
    if (!a || !b || a.lat == null || b.lat == null) return;
    const line = L.polyline(
      [[a.lat, a.lng], [b.lat, b.lng]],
      {
        color: e.blocked ? '#9ca3af' : '#374151',
        weight: e.blocked ? 2 : 3,
        opacity: e.blocked ? 0.5 : 0.7,
        dashArray: e.blocked ? '6,6' : null,
      }
    );
    line.bindPopup(`
      <div class="popup-content">
        <div class="id">${escapeHtml(e.from)} → ${escapeHtml(e.to)}</div>
        <div class="label">Edge</div>
        <div class="desc">${escapeHtml(e.instruction)}</div>
        <div class="meta">
          ${e.distance_meters ?? '?'} m · ${e.walk_minutes ?? '?'} min
          ${e.blocked ? ' · <strong style="color:#dc2626">BLOCKED</strong>' : ''}
        </div>
      </div>
    `);
    line.addTo(layerGroup);
  });

  // Index departments by building. Match a dept's building against an
  // entrance node's label using exact OR substring (either direction)
  // so minor naming drift between OSM ("MGH Yawkey Center") and the
  // facility JSON ("Yawkey Center") still groups correctly.
  const deptsByBuilding = {};
  for (const dept of (f.facility.departments || [])) {
    const key = (dept.building || '').toLowerCase().trim();
    if (!key) continue;
    (deptsByBuilding[key] ||= []).push(dept);
  }
  function deptsForLabel(label) {
    const k = (label || '').toLowerCase().trim();
    if (!k) return [];
    if (deptsByBuilding[k]) return deptsByBuilding[k];
    // Fuzzy: dept building substring of label, or label substring of dept building.
    const matches = [];
    for (const [bldKey, depts] of Object.entries(deptsByBuilding)) {
      if (k.includes(bldKey) || bldKey.includes(k)) {
        matches.push(...depts);
      }
    }
    return matches;
  }

  nodes.forEach(n => {
    if (n.lat == null || n.lng == null) return;
    points.push([n.lat, n.lng]);
    const color = TYPE_COLORS[n.type] ?? '#374151';
    const radius = TYPE_RADIUS[n.type] ?? 6;
    const marker = L.circleMarker([n.lat, n.lng], {
      radius,
      color: '#fff',
      weight: 2,
      fillColor: color,
      fillOpacity: 0.95,
    });
    // Show department count on entrance nodes that have any.
    const matchedDepts = (n.type === 'entrance' && n.label)
      ? deptsForLabel(n.label)
      : [];
    const labelText = matchedDepts.length > 0
      ? `${n.label} (${matchedDepts.length})`
      : n.label;
    marker.bindTooltip(labelText, {
      permanent: true,
      direction: 'top',
      offset: [0, -radius - 2],
      className: 'node-label',
    });
    const deptsHtml = matchedDepts.length
      ? `<div class="depts">
           <div class="depts-header">Departments here:</div>
           <ul>${matchedDepts.map(d =>
             `<li><strong>${escapeHtml(d.name)}</strong>${d.floor ? ` <span class="floor">· ${escapeHtml(d.floor)}</span>` : ''}</li>`
           ).join('')}</ul>
         </div>`
      : '';
    marker.bindPopup(`
      <div class="popup-content">
        <div class="id">${escapeHtml(n.id)} · ${escapeHtml(n.type)}</div>
        <div class="label">${escapeHtml(n.label)}</div>
        ${n.description ? `<div class="desc">${escapeHtml(n.description)}</div>` : ''}
        ${(n.keywords && n.keywords.length)
          ? `<div class="kw">keywords: ${n.keywords.map(escapeHtml).join(', ')}</div>` : ''}
        ${deptsHtml}
        <div class="meta">${(n.lat ?? 0).toFixed(5)}, ${(n.lng ?? 0).toFixed(5)}</div>
      </div>
    `, { maxWidth: 360 });
    marker.addTo(layerGroup);
  });

  if (points.length) {
    map.fitBounds(L.latLngBounds(points), { padding: [40, 40] });
  }
}

select.addEventListener('change', e => renderFacility(parseInt(e.target.value, 10)));
document.getElementById('showOsm').addEventListener('change', e => {
  if (e.target.checked) osmLayer.addTo(map);
  else map.removeLayer(osmLayer);
});
renderFacility(0);
</script>
</body>
</html>
"""


def main():
    facilities = load_facilities()
    if not facilities:
        raise SystemExit(f"No facility/topology JSON pairs found in {FACILITY_DIR}")

    payload = json.dumps(facilities, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__FACILITIES_JSON__", payload)
    OUT.write_text(html)
    print(f"Wrote {OUT}")
    print(f"  {len(facilities)} facilities embedded:")
    for f in facilities:
        n = len(f["topology"]["nodes"])
        e = len(f["topology"]["edges"])
        print(f"    {f['facility']['name']}: {n} nodes, {e} edges")
    print(f"\nOpen with: open {OUT}")


if __name__ == "__main__":
    main()
