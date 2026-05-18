"""
Filesystem layout for the Atlas backend.

Two workspaces are shared with the rest of the repo via symlinks/path-sharing
so atlas, the Flutter app, the training pipeline, and the standalone tools/
CLI all see the same data:

- `atlas/data/facilities/` is a symlink to `health_wayfinder/assets/facilities/`
  (the source of truth for shipped data).
- `BOOTSTRAP_DIR` defaults to `tools/bootstrap/` — the same scratch directory
  the standalone `tools/` CLI scripts read and write to. Atlas's authoring
  flow and the manual runbook share one workspace per slug.

Atlas-only state (`proposals/` for per-user drafts, `roles.yaml` for auth)
stays under `atlas/data/`.

For container deploys, override the ATLAS_*_DIR env vars below to point at
bind-mounted volumes — the symlink and tools/bootstrap default are local-dev
conveniences, the env vars are the deployment knob.
"""

from __future__ import annotations

import os
from pathlib import Path

# atlas/backend/app/paths.py -> atlas/backend/app -> atlas/backend -> atlas
ATLAS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT  = ATLAS_ROOT.parent

# Data directories — overridable via env so the same image runs locally and
# in a container with bind mounts.
FACILITIES_DIR = Path(
    os.environ.get("ATLAS_FACILITIES_DIR", ATLAS_ROOT / "data" / "facilities")
)
# Shared with the tools/ CLI runbook — see tools/INSTRUCTIONS.md.
BOOTSTRAP_DIR = Path(
    os.environ.get("ATLAS_BOOTSTRAP_DIR", REPO_ROOT / "tools" / "bootstrap")
)
# Per-user personal drafts created by contributors via the fork → edit → submit
# flow. Each <author>/<slug>/ subdir mirrors the bootstrap layout: facility.json,
# topology.json, optional proposal.json sidecar.
PROPOSALS_DIR = Path(
    os.environ.get("ATLAS_PROPOSALS_DIR", ATLAS_ROOT / "data" / "proposals")
)
# Tier config: admin (single login) + facility_editors (list).
ROLES_FILE = Path(
    os.environ.get("ATLAS_ROLES_FILE", ATLAS_ROOT / "data" / "roles.yaml")
)


def assert_repo_layout() -> None:
    """Fail loud at startup if the data directories are missing."""
    missing = [p for p in (FACILITIES_DIR, BOOTSTRAP_DIR) if not p.exists()]
    if missing:
        raise RuntimeError(
            "Atlas backend can't find its data directories. Missing:\n  "
            + "\n  ".join(str(p) for p in missing)
            + "\n\nDid you forget to seed atlas/data/?"
        )
    # Created lazily on first contributor fork — no fail-loud needed.
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
