#!/usr/bin/env python3
"""
Bootstrap a new facility from OpenStreetMap data.

Given a slug + an address or facility name, this script:
  1. Geocodes the query via Nominatim (free, no API key)
  2. Queries Overpass for every relevant feature (buildings, parking,
     transit stops, named landmarks) inside the geocoded bounding box
  3. Filters out residential noise (houses, sheds, garages)
  4. Computes a centroid for every polygon
  5. Writes three files into tools/bootstrap/<slug>/:
       osm.json
         — Reference layer for the topology viewer/editor (translucent
           building outlines you can drag topology nodes onto).
       facility.json
         — Pre-populated facility JSON with real building names and
           coords, ready to drop departments into.
       topology.json
         — Pre-populated topology with one parking node per real lot
           and one entrance node per real building. NO edges — you
           draw those in the editor based on real walking paths.

Usage:
  env/bin/python tools/fetch_osm_for_facility.py <slug> "<address or name>"

Examples:
  env/bin/python tools/fetch_osm_for_facility.py kaiser_panorama_city \\
      "Kaiser Permanente Panorama City Medical Center"
  env/bin/python tools/fetch_osm_for_facility.py mass_general \\
      "55 Fruit St, Boston, MA 02114"

Once it succeeds:
  1. Open tools/topology_editor.html
  2. Click Import JSON, paste contents of tools/bootstrap/<slug>/topology.json
  3. Add edges between nodes by clicking pairs in Add Edge mode
  4. Author landmark-rich instructions on each edge
  5. Export, save to health_wayfinder/assets/facilities/<slug>.topology.json

Be polite to free public APIs:
  - Nominatim: max 1 request/sec, must send a real User-Agent
  - Overpass: 1-2 req/sec, fail gracefully on 429
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlencode

import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"
USER_AGENT = "HealthWayfinder/1.0 (https://github.com/anthropics/claude-code; bootstrap)"


def http_get_json(url: str, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Rate-limited, waiting {wait}s…", file=sys.stderr)
                time.sleep(wait)
                continue
            raise


def http_post_json(url: str, body: str, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=body.encode("utf-8"), headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 504) and attempt < max_retries - 1:
                wait = 5 * (attempt + 1)
                print(f"  Server busy ({e.code}), waiting {wait}s…", file=sys.stderr)
                time.sleep(wait)
                continue
            raise


def _short_address(addr: dict, fallback: str) -> str:
    """Build "<house> <road>, <city>, <state> <postcode>" from Nominatim's
    structured address dict. Falls back to the raw display_name if the
    structured fields are missing.

    Nominatim populates these fields for any geocoded place:
      house_number, road, city|town|village, state, state_code, postcode,
      country, country_code.
    """
    house = addr.get("house_number")
    road = addr.get("road")
    city = addr.get("city") or addr.get("town") or addr.get("village")
    state = addr.get("state_code") or addr.get("state")
    postcode = addr.get("postcode")

    street = f"{house} {road}" if house and road else road
    locality = " ".join(p for p in [state, postcode] if p)

    pieces = [p for p in [street, city, locality] if p]
    return ", ".join(pieces) if pieces else fallback


def geocode(query: str) -> dict:
    """Resolve a free-text address/name to lat/lng + bounding box."""
    print(f"Geocoding: {query!r}")
    url = "https://nominatim.openstreetmap.org/search?" + urlencode({
        "format": "json",
        "q": query,
        "limit": 1,
        "addressdetails": 1,
    })
    results = http_get_json(url)
    if not results:
        raise SystemExit(f"No geocoder result for {query!r}")
    r = results[0]
    bbox = [float(x) for x in r["boundingbox"]]  # [south, north, west, east]
    print(f"  → {r['display_name']}")
    print(f"  → center {r['lat']}, {r['lon']}")
    print(f"  → bbox   south={bbox[0]} north={bbox[1]} west={bbox[2]} east={bbox[3]}")
    return {
        "name": r["display_name"].split(",")[0],
        "full_name": r["display_name"],
        "lat": float(r["lat"]),
        "lng": float(r["lon"]),
        "bbox": bbox,
        "address": r.get("address", {}),
    }


def overpass_query(bbox: list[float], padding_deg: float = 0.0015) -> list[dict]:
    """Pull every relevant feature inside the bounding box (with a small pad)."""
    s = bbox[0] - padding_deg
    n = bbox[1] + padding_deg
    w = bbox[2] - padding_deg
    e = bbox[3] + padding_deg
    box = f"{s},{w},{n},{e}"
    query = f"""
    [out:json][timeout:60];
    (
      way["building"]({box});
      way["amenity"="parking"]({box});
      way["amenity"="hospital"]({box});
      way["amenity"="clinic"]({box});
      way["amenity"="cafe"]({box});
      way["healthcare"]({box});
      way["highway"="footway"]({box});
      way["public_transport"="platform"]({box});
      relation["building"]({box});
      relation["amenity"="hospital"]({box});
    );
    out geom;
    """
    print(f"Querying Overpass for features in bbox {box}…")
    data = http_post_json(
        "https://overpass-api.de/api/interpreter",
        "data=" + quote(query),
    )
    return data.get("elements", [])


# Tags that mean "irrelevant clutter" and should be filtered out.
NOISE_BUILDING_TAGS = {
    "house", "residential", "apartments", "detached", "terrace",
    "garage", "garages", "carport", "shed", "roof", "hut",
    "static_caravan", "barn",
}

# Hint phrases that indicate a feature IS relevant (named with one of these).
RELEVANT_NAME_HINTS = (
    "medical", "hospital", "clinic", "urgent care", "emergency",
    "pharmacy", "imaging", "lab", "wing", "tower", "annex",
    "tram", "shuttle", "cafe", "coffee", "shop",
)


# Street-level landmarks worth emitting when --include-landmarks is on. Used
# for re-orientation in dense urban facilities (clinics in commercial areas)
# where patients describe their location by storefront, not building name.
LANDMARK_AMEN = {"restaurant", "fast_food", "pharmacy", "bicycle_rental",
                 "bank", "post_office", "library", "place_of_worship",
                 "fuel", "fountain"}
LANDMARK_SHOP_ANY = True  # shop=* with a name


def is_relevant(el: dict, include_landmarks: bool = False) -> bool:
    tags = el.get("tags", {}) or {}
    name = (tags.get("name") or "").lower()
    bld = tags.get("building") or ""
    amen = tags.get("amenity") or ""
    hc = tags.get("healthcare") or ""

    # Always relevant: hospital/clinic/healthcare/parking
    if amen in ("hospital", "clinic", "parking", "doctors", "cafe"):
        return True
    if hc:
        return True

    # Building tag — keep hospital/commercial/yes; reject residential noise.
    if bld:
        if bld in NOISE_BUILDING_TAGS:
            # ...but if it has a relevant name, override.
            return any(h in name for h in RELEVANT_NAME_HINTS)
        return True

    # Footways, transit platforms — keep for context.
    if tags.get("highway") == "footway" or tags.get("public_transport"):
        return True

    # Named features that look medical/transit-relevant.
    if any(h in name for h in RELEVANT_NAME_HINTS):
        return True

    # Optional: street-level landmarks for urban-clinic re-orientation.
    if include_landmarks and name:
        if amen in LANDMARK_AMEN:
            return True
        if LANDMARK_SHOP_ANY and tags.get("shop"):
            return True

    return False


def centroid(geom: list[dict]) -> tuple[float, float]:
    lats = [p["lat"] for p in geom]
    lngs = [p["lon"] for p in geom]
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "node"


def is_reference_worthy(el: dict) -> bool:
    """Stricter than is_relevant — only the polygons worth drawing on the
    reference layer. Drops generic urban context (unnamed building=yes)
    that would clutter the map without helping topology authoring."""
    tags = el.get("tags", {}) or {}
    name = (tags.get("name") or "").lower()
    bld = tags.get("building") or ""
    amen = tags.get("amenity") or ""
    hc = tags.get("healthcare") or ""

    if bld == "hospital":
        return True
    if amen in ("hospital", "parking", "clinic"):
        return True
    if bld == "parking":
        return True
    if hc:
        return True
    if amen == "cafe" and name:
        return True
    if any(h in name for h in RELEVANT_NAME_HINTS):
        return True
    return False


def build_reference_layer(features: list[dict], facility_id: str) -> dict:
    """Polygon outlines + sidewalk segments for the viewer/editor reference
    layer. Footways power the auto-edge drafter (draft_edges_for_facility.py)
    so authored edges follow real paths instead of straight lines."""
    polygons, footways = [], []
    for el in features:
        if not el.get("geometry"):
            continue
        tags = el.get("tags", {}) or {}
        if tags.get("highway") == "footway":
            footways.append({
                "name": tags.get("name", ""),
                "path": [[round(p["lat"], 6), round(p["lon"], 6)]
                         for p in el["geometry"]],
            })
            continue
        if not is_reference_worthy(el):
            continue
        polygons.append({
            "name": tags.get("name", ""),
            "building": tags.get("building", ""),
            "amenity": tags.get("amenity", ""),
            "healthcare": tags.get("healthcare", ""),
            "polygon": [[round(p["lat"], 6), round(p["lon"], 6)]
                        for p in el["geometry"]],
        })
    return {
        "facility_id": facility_id,
        "source": "OpenStreetMap Overpass API",
        "features": polygons,
        "footways": footways,
    }


def build_facility_bootstrap(slug: str, geo: dict, features: list[dict]) -> dict:
    """A facility.json template with real building names and coords."""
    buildings = []
    parking = []
    seen_names = set()
    for el in features:
        if not el.get("geometry"):
            continue
        tags = el.get("tags", {}) or {}
        name = tags.get("name", "")
        amen = tags.get("amenity", "")
        bld = tags.get("building", "")
        lat, lng = centroid(el["geometry"])
        lat = round(lat, 5)
        lng = round(lng, 5)

        is_parking = amen == "parking" or bld == "parking"
        # Match any patient-facing healthcare facility OSM might tag here:
        # full hospitals, outpatient clinics, doctor's offices, healthcare=*
        # buildings. Otherwise small clinics in commercial buildings (Atrius,
        # community health centers) get filtered out.
        hc = tags.get("healthcare", "")
        is_hospital = (
            bld == "hospital"
            or amen in ("hospital", "clinic", "doctors")
            or hc in ("hospital", "clinic", "doctor", "centre")
            or "Medical" in name
            or "Health" in name
            or "Hospital" in name
        )

        if is_parking:
            label = name or f"Parking ({lat:.4f},{lng:.4f})"
            if label in seen_names:
                continue
            seen_names.add(label)
            parking.append({
                "name": label,
                "nearest_buildings": [],
                "entrance_note": "TODO: describe how to walk from this lot toward campus.",
                "lat": lat,
                "lng": lng,
            })
        elif is_hospital and name:
            if name in seen_names:
                continue
            seen_names.add(name)
            buildings.append({"name": name, "lat": lat, "lng": lng})

    return {
        "id": slug,
        "name": geo["name"],
        "address": _short_address(geo["address"], geo["full_name"]),
        "type": "Hospital",
        "campus_description": (
            "TODO: write a 1-2 sentence campus description. "
            "What buildings exist, how parking is structured, distinctive "
            "features patients should look for."
        ),
        "buildings": sorted(buildings, key=lambda b: b["name"]),
        "parking": parking,
        "departments": [],
    }


def build_topology_bootstrap(slug: str, geo: dict, features: list[dict],
                              include_landmarks: bool = False) -> dict:
    """Pre-populated topology: one entrance + parking + transit node per real
    OSM feature. Edges left empty — author them in the editor."""
    nodes = []
    used_ids = set()

    def make_id(prefix: str, hint: str) -> str:
        base = f"{prefix}_{slugify(hint)}" if hint else prefix
        if base not in used_ids:
            used_ids.add(base)
            return base
        i = 2
        while f"{base}_{i}" in used_ids:
            i += 1
        used_ids.add(f"{base}_{i}")
        return f"{base}_{i}"

    for el in features:
        if not el.get("geometry"):
            continue
        tags = el.get("tags", {}) or {}
        name = tags.get("name", "")
        amen = tags.get("amenity", "")
        bld = tags.get("building", "")
        hc = tags.get("healthcare", "")
        public_t = tags.get("public_transport", "")
        lat, lng = centroid(el["geometry"])
        lat = round(lat, 5)
        lng = round(lng, 5)

        is_parking = amen == "parking" or bld == "parking"
        is_hospital = (
            bld == "hospital"
            or amen in ("hospital", "clinic", "doctors")
            or hc in ("hospital", "clinic", "doctor", "centre")
            or "Medical" in name
            or "Health" in name
            or "Hospital" in name
        )
        is_transit = public_t or "Tram" in name or "Bus" in name or "Shuttle" in name
        is_cafe = amen == "cafe" or "Coffee" in name or "Cafe" in name
        shop = tags.get("shop", "")
        is_landmark = include_landmarks and name and (
            amen in LANDMARK_AMEN or bool(shop)
        )

        if is_parking and name:
            nodes.append({
                "id": make_id("parking", name),
                "type": "parking",
                "label": name,
                "description": f"Parking area: {name}.",
                "keywords": [name.lower(), "parking"],
                "lat": lat, "lng": lng,
            })
        elif is_hospital and name:
            nodes.append({
                "id": make_id("entrance", name),
                "type": "entrance",
                "label": name,
                "description": f"{name} entrance. TODO: describe doors, signage.",
                "keywords": [name.lower()],
                "lat": lat, "lng": lng,
            })
        elif is_transit and name:
            nodes.append({
                "id": make_id("transit", name),
                "type": "transit",
                "label": name,
                "description": f"{name}. TODO: describe pickup spot.",
                "keywords": [name.lower()],
                "lat": lat, "lng": lng,
            })
        elif is_cafe and name:
            nodes.append({
                "id": make_id("landmark", name),
                "type": "landmark",
                "label": name,
                "description": f"{name} — visible campus landmark.",
                "keywords": [name.lower(), "coffee", "cafe"],
                "lat": lat, "lng": lng,
            })
        elif is_landmark:
            kind = shop or amen or "landmark"
            nodes.append({
                "id": make_id("landmark", name),
                "type": "landmark",
                "label": name,
                "description": f"{name} ({kind}) — visible street-level landmark.",
                "keywords": [name.lower(), kind.replace("_", " ")],
                "lat": lat, "lng": lng,
            })

    nodes = _dedupe_transit(nodes)

    return {
        "version": time.strftime("%Y-%m-%d") + "-osm-bootstrap",
        "facility_id": slug,
        "nodes": nodes,
        "edges": [],
    }


def _dedupe_transit(nodes: list[dict], radius_m: float = 30.0) -> list[dict]:
    """Cluster transit nodes by base name + proximity. OSM tags every separate
    public_transport=stop_position individually — for one rail platform you can
    end up with 4-6 near-identical nodes. Keep one per cluster."""
    R = 6371000

    def dist(a: dict, b: dict) -> float:
        import math
        dlat = math.radians(b["lat"] - a["lat"])
        dlng = math.radians(b["lng"] - a["lng"])
        x = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(a["lat"]))
             * math.cos(math.radians(b["lat"]))
             * math.sin(dlng / 2) ** 2)
        return 2 * R * math.atan2(math.sqrt(x), math.sqrt(1 - x))

    def base(label: str) -> str:
        # Strip parenthetical suffixes like " (Outbound)" so they cluster with siblings.
        s = re.sub(r"\s*\([^)]*\)\s*", " ", label)
        # Drop trailing platform descriptors after a hyphen ("Lansdowne - Commuter Rail - Outbound" -> "Lansdowne")
        s = s.split(" - ")[0]
        return s.strip().lower()

    out, kept_transits = [], []
    for n in nodes:
        if n["type"] != "transit":
            out.append(n)
            continue
        b = base(n["label"])
        match = next((k for k in kept_transits
                      if base(k["label"]) == b and dist(k, n) <= radius_m), None)
        if match:
            continue  # cluster duplicate
        kept_transits.append(n)
        out.append(n)
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Bootstrap a facility from OpenStreetMap.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("slug", help="Short identifier, e.g. 'kaiser_panorama_city'")
    ap.add_argument("query", help="Address or facility name to geocode")
    ap.add_argument("--padding", type=float, default=0.0015,
                    help="Bounding-box padding in degrees (default 0.0015 ~150m)")
    ap.add_argument("--include-landmarks", action="store_true",
                    help="Also emit nearby shops, restaurants, pharmacies as "
                         "landmark-type nodes. Useful for small urban clinics "
                         "where patients re-orient by storefronts. Adds noise "
                         "for big hospital campuses — leave off there.")
    args = ap.parse_args()

    TOOLS_DIR.mkdir(exist_ok=True)

    geo = geocode(args.query)
    time.sleep(1.0)  # polite to Nominatim
    elements = overpass_query(geo["bbox"], padding_deg=args.padding)
    print(f"  → {len(elements)} raw elements")

    features = [el for el in elements if is_relevant(el, args.include_landmarks)]
    print(f"  → {len(features)} relevant features after filtering")

    counts = {"hospital": 0, "parking": 0, "transit": 0, "cafe": 0,
              "landmark": 0, "other": 0}
    for el in features:
        tags = el.get("tags", {}) or {}
        if tags.get("building") == "hospital" or tags.get("amenity") == "hospital":
            counts["hospital"] += 1
        elif tags.get("amenity") == "parking" or tags.get("building") == "parking":
            counts["parking"] += 1
        elif tags.get("public_transport") or "Tram" in (tags.get("name") or ""):
            counts["transit"] += 1
        elif tags.get("amenity") == "cafe":
            counts["cafe"] += 1
        elif args.include_landmarks and (
            tags.get("amenity") in LANDMARK_AMEN or tags.get("shop")
        ):
            counts["landmark"] += 1
        else:
            counts["other"] += 1
    print(f"  breakdown: {counts}")

    if not features:
        raise SystemExit(
            "No relevant features found. Try a more specific query or "
            "increase --padding."
        )

    bootstrap_dir = TOOLS_DIR / "bootstrap" / args.slug
    bootstrap_dir.mkdir(parents=True, exist_ok=True)

    osm_layer = build_reference_layer(features, args.slug)
    osm_path = bootstrap_dir / "osm.json"
    osm_path.write_text(json.dumps(osm_layer, indent=2, ensure_ascii=False))
    print(f"\nWrote {osm_path.relative_to(ROOT)} ({len(osm_layer['features'])} polygons)")

    fac = build_facility_bootstrap(args.slug, geo, features)
    fac_path = bootstrap_dir / "facility.json"
    fac_path.write_text(json.dumps(fac, indent=2, ensure_ascii=False))
    print(f"Wrote {fac_path.relative_to(ROOT)} "
          f"({len(fac['buildings'])} buildings, {len(fac['parking'])} parking)")

    topo = build_topology_bootstrap(args.slug, geo, features,
                                     include_landmarks=args.include_landmarks)
    topo_path = bootstrap_dir / "topology.json"
    topo_path.write_text(json.dumps(topo, indent=2, ensure_ascii=False))
    print(f"Wrote {topo_path.relative_to(ROOT)} "
          f"({len(topo['nodes'])} nodes, 0 edges)")

    rel = bootstrap_dir.relative_to(ROOT)
    print("\nNext steps:")
    print(f"  1. Open tools/topology_editor.html")
    print(f"  2. Click Import JSON, paste contents of {rel}/topology.json")
    print(f"  3. Verify node positions on the map (drag if needed)")
    print(f"  4. Switch to Add Edge mode, draw walking paths between nodes")
    print(f"  5. Click each edge to add a landmark-rich instruction")
    print(f"  6. Export and save as health_wayfinder/assets/facilities/{args.slug}.topology.json")
    print(f"  7. Open {rel}/facility.json, fill in departments + campus_description,")
    print(f"     save as health_wayfinder/assets/facilities/{args.slug}.json")
    print(f"  8. Re-run: env/bin/python tools/build_topology_viewer.py")


if __name__ == "__main__":
    main()
