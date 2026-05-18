# Adding a new facility — runbook

End-to-end sequence to add a new hospital to the app. ~45 minutes total for a well-mapped urban hospital, of which ~30 is the manual editor work in step 3 (the irreducible craft layer).

---

## 0. Prerequisites

- `env/` venv set up (run `./scripts/setup.sh` from repo root if not).
- `training/.env` has `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` configured for your local LLM endpoint (llama-swap / Ollama / vLLM). Default model is `qwen3.5-122b`.
- Pick a slug (snake_case, no spaces): `brigham`, `cedars_sinai`, `mt_sinai`. This becomes the asset filename.

---

## 1. Bootstrap from OpenStreetMap (~5 sec, free)

```bash
env/bin/python tools/fetch_osm_for_facility.py <slug> "<address or facility name>"
```

**Example:**
```bash
env/bin/python tools/fetch_osm_for_facility.py brigham \
    "Brigham and Women's Hospital, Boston"
```

Writes three files into `tools/bootstrap/<slug>/`:

| File | Purpose |
|---|---|
| `osm.json` | Building polygon footprints — reference layer for the editor/viewer |
| `facility.json` | Facility template with real building names + lat/lngs, empty `departments: []` |
| `topology.json` | Topology with one entrance node per building, parking node per lot, transit nodes — empty `edges: []` |

**If 0 nodes:** the hospital is sparsely tagged in OSM (common for small clinics). Skip to step 3 and hand-author nodes in the editor.

**For small urban clinics** (single building in a commercial district), add `--include-landmarks` to also emit nearby shops, restaurants, and pharmacies as `landmark`-type nodes. Patients in dense urban areas re-orient by storefront ("I'm by the Star Market") more than by building name. Leave the flag off for big multi-building hospital campuses — landmark noise outside the campus isn't useful there.

---

## 2. Extract departments via local LLM (~60–90 sec, free)

Find 3–8 hospital website URLs covering the major service lines. Look for "Locations", "Departments", "Maps and Directions" pages on the hospital's own site.

```bash
env/bin/python tools/fetch_departments_for_facility.py <slug> \
    --url "https://www.example.org/locations" \
    --url "https://www.example.org/services" \
    --url "https://www.example.org/maps-and-directions" \
    --merge
```

Without `--merge`, prints to stdout for inspection. With `--merge`, writes departments back into `tools/bootstrap/<slug>/facility.json`.

The model is constrained to the closed list of OSM building names — it can't invent buildings. Confidence levels print to stderr; review any `low` entries against the source before promoting.

---

## 2b. Auto-draft edges (~5 sec, optional but recommended)

```bash
env/bin/python tools/draft_edges_for_facility.py <slug> --write
```

For each entrance node, drafts edges to every nearby parking, landmark, transit, and other-entrance node within walking distance. Routes via OSM footways when possible (real sidewalk geometry, stored as a polyline) and falls back to straight-line where endpoints can't snap to a sidewalk.

You'll still need to refine instruction text in the editor (each draft edge ships with a TODO stub), but you skip the click-pair-by-pair authoring step entirely. Re-running is idempotent — only adds edges that don't already exist.

Without `--write`, prints proposed edges to stdout for inspection. Use `--max-dist N` to cap default edge length (default 800m).

## 3. Refine in the editor (~15 min after auto-drafting, the only manual step)

```bash
open tools/topology_editor.html
```

Then in the browser:

1. **Import JSON** → paste contents of `tools/bootstrap/<slug>/topology.json`
2. (Optional) Use the address search at top to anchor the map on the campus.
3. **Drag any nodes** whose OSM centroid is wrong — e.g. you want the entrance on the patient-facing side of a building, not the geometric center.
4. **Add Edge** mode → click pairs of nodes to draw walking paths. Distance + walk-minutes auto-fill from coordinates. Write the patient-facing instruction prose for each edge (landmark-rich, not turn-by-turn).
5. **Add Node** mode → for landmarks OSM doesn't have (signage, fountains, decorative features patients describe when lost).
6. **Export JSON** → save as `health_wayfinder/assets/facilities/<slug>.topology.json`.

The editor autosaves to `localStorage`, so you can close the tab and resume.

**Suggested edges:**
- Every parking node connected to the nearest entrance(s)
- Every transit/T-stop node connected to a primary entrance
- Cross-building paths between major patient destinations

**Multi-entrance authoring (the highest-leverage craft step):**

The bootstrap gives you ONE entrance node per building (the OSM centroid). Real buildings have multiple entrances — main lobby, Urgent Care side door, ED ambulance bay, accessible ramp, after-hours door — and "wrong door" is the wayfinding failure this app exists to solve. Adding extra entrance nodes is the difference between a directory and an actual wayfinder, especially at single-building facilities.

For each real entrance you can identify (Street View, site visit, or facility's "find us" page):

1. Add an `entrance`-type node at the actual door coordinates (drag, don't use the building centroid).
2. Use a snake_case `id` like `entrance_atrius_urgent_care` and a label like "Atrius — Urgent Care entrance".
3. Write a `description` that names the visible cue from the sidewalk: signage, awning, ramp, distinctive feature.
4. Author edges from every relevant parking / transit node to this entrance with landmark-rich prose.
5. In the facility JSON, set `topology_node_id` on each department that uses this entrance instead of the main one. Departments without `topology_node_id` fall back to building-name match and use the first entrance — that's correct for shared-lobby departments, only override when the patient should NOT use the main door.

Kaiser Panorama City is the canonical example: ED and Radiology share the "Hospital" building but pin different entrances (`emergency_entrance` vs `hospital_main_entrance`).

---

## 4. Promote bootstrap files into the app

```bash
cp tools/bootstrap/<slug>/facility.json \
   health_wayfinder/assets/facilities/<slug>.json
# (the topology was already saved from the editor in step 3)
```

The `pubspec.yaml` already globs `assets/facilities/`, so no manifest edit needed.

---

## 4b. Validate before shipping (~1 sec, free)

```bash
env/bin/python tools/validate_facility.py <slug> --promoted
```

Catches the failure modes that silently degrade UX once the facility ships:

- Department `directions` / `check_in` text matching website-redirect placeholders ("Visit the X website", "Available at select X locations") — the model echoes these as wayfinding steps and defeats the whole point of the app.
- User-facing fields containing literal `TODO`.
- Parking with empty `nearest_buildings` everywhere — origin auto-select fails, topology routing falls through to the department's `directions` text even when a real route exists.
- `topology_node_id` references that don't resolve.
- Topology edge `instruction` strings still containing `TODO` (these are shown verbatim as walking steps).

Exits non-zero on any violation. Validate every promoted facility at once with `--all`.

If the validator fails: re-open the editor (step 3), fill in the missing prose, re-export, and re-promote (step 4). Don't ship a facility that fails this check — the app will produce nonsense like "Visit the X website to find directions" as step 1 of the carousel.

---

## 5. Expand aliases (~30 sec, free)

```bash
env/bin/python tools/fetch_aliases_for_facility.py <slug> --merge
```

Each department starts with 2–3 aliases from step 2 and ends with ~10 (English colloquialisms, Spanish synonyms, abbreviations, common misspellings). Run after step 4 because it operates on the promoted file.

---

## 6. Register in the Flutter app

**Nothing to do.** The app auto-discovers any `assets/facilities/*.json` at startup via the asset manifest. Dropping the file in step 4 is the registration step.

The id, display name, address, and type are all read from the JSON itself — no Dart edits, no picker list to maintain.

---

## 7. Sanity-check the topology

```bash
env/bin/python tools/build_topology_viewer.py
open tools/topology_viewer.html
```

Read-only Leaflet map of every facility. Click any entrance node — popup shows departments mapped to that building. Look for:
- Orphan nodes (no edges)
- Edges crossing through buildings
- Departments mapped to the wrong building

---

## 8. Verify

```bash
env/bin/python tools/validate_facility.py --all          # final lint pass on all facilities
./scripts/check.sh                                       # analyze + tests
cd health_wayfinder && flutter run --dart-define=GEMMA_MODE=ollama
```

In the running app: pick the new facility, ask for a few departments, confirm routes render as multi-step carousels (not the prose `directions` fallback).

---

## File hygiene

- **`tools/bootstrap/<slug>/`** is scratch work. `osm.json` is worth committing as the reference layer for the lifetime of the facility (regenerate when buildings change). `facility.json` and `topology.json` become stale once promoted into `assets/facilities/` — feel free to delete or `.gitignore`.
- The viewer (`tools/topology_viewer.html`) is regenerated; don't hand-edit.
- Promoted files in `health_wayfinder/assets/facilities/` are the source of truth and get committed.
