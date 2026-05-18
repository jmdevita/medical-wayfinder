"""
Slug → file path resolver shared by every service. Falls back from bootstrap
drafts to published assets, mirroring _resolve_paths in routes/facilities.py.
"""

from __future__ import annotations

from pathlib import Path

from app.paths import BOOTSTRAP_DIR, FACILITIES_DIR


def resolve_paths(slug: str) -> tuple[Path, Path, str]:
    """Return (facility_path, topology_path, source) for a slug."""
    bootstrap_dir = BOOTSTRAP_DIR / slug
    if bootstrap_dir.exists() and (bootstrap_dir / "facility.json").exists():
        return (
            bootstrap_dir / "facility.json",
            bootstrap_dir / "topology.json",
            "bootstrap",
        )
    return (
        FACILITIES_DIR / f"{slug}.json",
        FACILITIES_DIR / f"{slug}.topology.json",
        "published",
    )


def osm_path_for(slug: str) -> Path:
    """Where bootstrap stashed the OSM reference layer."""
    return BOOTSTRAP_DIR / slug / "osm.json"


def suggestions_path_for(slug: str) -> Path:
    """Sidecar of pending Street View edge-walker suggestions for a slug.

    Lives next to osm.json under the bootstrap dir so it travels with the
    in-progress draft.
    """
    return BOOTSTRAP_DIR / slug / "suggestions.json"
