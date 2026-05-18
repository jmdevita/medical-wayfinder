#!/usr/bin/env python3
"""
Lint pass on a facility's data before it's promoted into the Flutter app.

Run this between editor work (step 3 of the runbook) and promotion to
`health_wayfinder/assets/facilities/` (step 4). It catches the kinds of
bootstrap-residue and mis-wirings that silently degrade UX:

- Department `directions` / `check_in` / `directions_by_origin` strings
  matching known placeholder patterns ("Visit the X website", "Available
  at select X locations", "Locations vary; check the website", etc.).
  These reach the patient as wayfinding steps and defeat the whole point
  of the app — the model is supposed to distill the website, not redirect
  to it.
- Any user-facing field containing a literal "TODO".
- Parking with empty `nearest_buildings` for *every* entry. The orchestrator
  uses this list to auto-pick a parking origin when the patient hasn't
  named one. If it's empty everywhere, routing falls through to the
  department's `directions` text — even when the topology graph has a
  valid route.
- Parking `nearest_buildings` referencing buildings that don't exist in
  the facility's `buildings[]` list or any department's `building` field.
- Department `topology_node_id` references that don't resolve in the
  matching `<slug>.topology.json`.
- Topology edge `instruction` text containing "TODO" — these are the
  literal strings shown to the patient as walking steps.

Usage:
  env/bin/python tools/validate_facility.py <slug>            # validates the bootstrap copy
  env/bin/python tools/validate_facility.py <slug> --promoted # validates the assets copy
  env/bin/python tools/validate_facility.py --all             # validates every promoted facility

Exits non-zero on any violation so it can gate CI / a wrapper script.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "health_wayfinder" / "assets" / "facilities"
BOOTSTRAP_DIR = ROOT / "tools" / "bootstrap"


# Patterns that should never appear in a user-facing field. Each one is a
# fingerprint of bootstrap stub text or website-redirect copy that defeats
# the app's distillation purpose.
PLACEHOLDER_PATTERNS = [
    re.compile(r"\bvisit the .+ website\b", re.IGNORECASE),
    re.compile(r"\bcheck the .+ website\b", re.IGNORECASE),
    re.compile(r"\bfind a location\b", re.IGNORECASE),
    re.compile(r"\bavailable at select .+ (location|practice)", re.IGNORECASE),
    re.compile(r"\blocated within .+ (building|practice)", re.IGNORECASE),
    re.compile(r"\blocations vary\b", re.IGNORECASE),
    re.compile(r"\bTODO\b"),
]


class Violations:
    """Collects validation failures with file context for grouped reporting."""

    def __init__(self, facility_path: Path):
        self.facility_path = facility_path
        self.errors: list[str] = []

    def add(self, msg: str) -> None:
        self.errors.append(msg)

    def __bool__(self) -> bool:
        return bool(self.errors)

    def report(self) -> None:
        rel = self.facility_path.relative_to(ROOT)
        if not self.errors:
            print(f"OK   {rel}")
            return
        print(f"FAIL {rel}  ({len(self.errors)} issues)")
        for e in self.errors:
            print(f"  - {e}")


def _check_placeholder(value: object, where: str, v: Violations) -> None:
    if not isinstance(value, str):
        return
    for pat in PLACEHOLDER_PATTERNS:
        if pat.search(value):
            v.add(f'{where} matches placeholder /{pat.pattern}/: "{value}"')
            return


def validate_departments(facility: dict, v: Violations) -> None:
    for dept in facility.get("departments", []) or []:
        name = dept.get("name", "<unnamed>")
        for field in ("directions", "check_in"):
            _check_placeholder(dept.get(field), f'department "{name}" {field}', v)
        dir_map = dept.get("directions_by_origin")
        if isinstance(dir_map, dict):
            for origin, text in dir_map.items():
                _check_placeholder(
                    text,
                    f'department "{name}" directions_by_origin[{origin}]',
                    v,
                )


def validate_parking(facility: dict, v: Violations) -> None:
    parking = facility.get("parking", []) or []
    if not parking:
        return  # facilities without parking are valid (urban transit-only)

    wired = [p for p in parking if (p.get("nearest_buildings") or [])]
    if not wired:
        v.add(
            "no parking entry has nearest_buildings populated — origin "
            "auto-select will fail and routing will fall back to the "
            "department's directions text"
        )

    named_buildings = {
        b["name"]
        for b in (facility.get("buildings", []) or [])
        if isinstance(b, dict) and isinstance(b.get("name"), str)
    }
    dept_buildings = {
        d["building"]
        for d in (facility.get("departments", []) or [])
        if isinstance(d, dict) and isinstance(d.get("building"), str)
    }
    all_buildings = named_buildings | dept_buildings

    for p in parking:
        name = p.get("name", "<unnamed>")
        for b in p.get("nearest_buildings", []) or []:
            if all_buildings and b not in all_buildings:
                v.add(
                    f'parking "{name}" lists nearest_building "{b}" but no '
                    f"building or department uses that name"
                )
        note = p.get("entrance_note")
        if isinstance(note, str) and "TODO" in note:
            v.add(f'parking "{name}" entrance_note still contains TODO: "{note}"')


def validate_topology_links(
    facility: dict, topology_path: Path, v: Violations
) -> None:
    if not topology_path.exists():
        return
    try:
        topology = json.loads(topology_path.read_text())
    except json.JSONDecodeError as e:
        v.add(f"topology file parse error: {e}")
        return

    node_ids = {
        n["id"] for n in topology.get("nodes", []) or [] if isinstance(n.get("id"), str)
    }

    for dept in facility.get("departments", []) or []:
        ref = dept.get("topology_node_id")
        if isinstance(ref, str) and ref not in node_ids:
            v.add(
                f'department "{dept.get("name", "<unnamed>")}" '
                f'topology_node_id "{ref}" not found in '
                f"{topology_path.name}"
            )

    for edge in topology.get("edges", []) or []:
        instr = edge.get("instruction")
        if isinstance(instr, str) and "TODO" in instr:
            v.add(
                f'topology edge {edge.get("from")} -> {edge.get("to")} '
                f'instruction still contains TODO: "{instr}"'
            )


def validate_facility_file(facility_path: Path) -> Violations:
    v = Violations(facility_path)
    try:
        facility = json.loads(facility_path.read_text())
    except FileNotFoundError:
        v.add("file not found")
        return v
    except json.JSONDecodeError as e:
        v.add(f"parse error: {e}")
        return v

    validate_departments(facility, v)
    validate_parking(facility, v)

    topology_path = facility_path.with_name(facility_path.stem + ".topology.json")
    validate_topology_links(facility, topology_path, v)
    return v


def resolve_paths(slug: str | None, promoted: bool, all_promoted: bool) -> list[Path]:
    if all_promoted:
        return sorted(
            p
            for p in ASSETS_DIR.glob("*.json")
            if not p.name.endswith(".topology.json")
        )
    if not slug:
        sys.exit("error: <slug> is required unless --all is given")
    if promoted:
        return [ASSETS_DIR / f"{slug}.json"]
    return [BOOTSTRAP_DIR / slug / "facility.json"]


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", nargs="?", help="facility slug (e.g. atrius_boston_kenmore)")
    parser.add_argument(
        "--promoted",
        action="store_true",
        help="validate the promoted asset under health_wayfinder/assets/facilities/ "
        "rather than the bootstrap copy under tools/bootstrap/<slug>/",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_promoted",
        help="validate every promoted facility under health_wayfinder/assets/facilities/",
    )
    args = parser.parse_args(argv)

    paths = resolve_paths(args.slug, args.promoted, args.all_promoted)
    any_failed = False
    for path in paths:
        v = validate_facility_file(path)
        v.report()
        if v:
            any_failed = True
    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
