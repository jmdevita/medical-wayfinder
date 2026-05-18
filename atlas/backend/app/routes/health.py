"""
Liveness and readiness probes for orchestrators.

  - `/live` — process is up, the event loop is responsive. Cheap.
  - `/ready` — also verifies that the data directories exist and are readable;
              orchestrators should withhold traffic until this returns 200.
  - `/health` — alias for `/live` so existing local checks keep working.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.paths import BOOTSTRAP_DIR, FACILITIES_DIR

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> dict[str, object]:
    """
    Returns 503 if the data directories are missing — common reason a fresh
    container would be unable to serve real traffic.
    """
    issues: list[str] = []
    if not FACILITIES_DIR.exists():
        issues.append(f"facilities_dir missing: {FACILITIES_DIR}")
    if not BOOTSTRAP_DIR.exists():
        issues.append(f"bootstrap_dir missing: {BOOTSTRAP_DIR}")
    if issues:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "issues": issues})
    return {
        "status": "ready",
        "facilities_dir": str(FACILITIES_DIR),
        "bootstrap_dir":  str(BOOTSTRAP_DIR),
    }
