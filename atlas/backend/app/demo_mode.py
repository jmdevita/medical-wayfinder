"""
Public-demo gating for the Atlas backend.

Set ATLAS_DEMO_MODE=true on a deployment that hosts Atlas publicly with
periodic state resets (see scripts/demo-entrypoint.sh + the daily restart
workflow). Demo mode does three things:

1. **Blocks endpoints that cost real money or external API quota.**
   - LLM-driven jobs (extract-departments, expand-aliases,
     streetview-edges bulk)
   - Per-edge Street View regenerate + pano proxy (Google Maps Static SKU)
   - OSM bootstrap (Nominatim + Overpass; free but per-IP rate-limited
     enough that a scraper could get our IP banned)

   Publish is deliberately **left open** so judges can experience the full
   "author -> publish" demo flow. The daily reset re-seeds /data so any
   publishes get rolled back on the next container restart — matches the
   paperless-ngx pattern of "destructive things are safe."

2. **Surfaces a `demo_mode: true` flag via `/api/config`** so the frontend
   can render a banner explaining the reset cadence.

3. **Leaves everything else open** — read facility data, browse topology,
   edit topology graphs, add/remove departments, run the deterministic
   draft-edges path (no LLM cost), accept/discard Street View suggestions
   that were prebaked in the seed data, publish to /data (reset-protected).
   That gives judges enough to actually *use* the tool without spending OPEX
   or hitting third-party rate limits.

Why a separate module instead of just rate-limit-to-zero? Two reasons:
the failure mode is different (a clear 503 with a "demo mode" message is
friendlier than a 429), and `demo_block` composes cleanly into FastAPI
dependency stacks (`Depends(demo_block)`).

The ATLAS_AUTH_ENABLED + ATLAS_RATE_LIMIT_ENABLED env vars are independent
and orthogonal — demo mode does not imply either. Production deployments
typically run with AUTH on and DEMO off; the public demo runs both off
(auth) and on (demo).
"""

from __future__ import annotations

import os

from fastapi import HTTPException, status


def is_demo_mode() -> bool:
    """True if ATLAS_DEMO_MODE is set to a truthy value.

    Read fresh from env on every call rather than module-load so tests can
    monkey-patch via `monkeypatch.setenv` without re-importing.
    """
    return os.environ.get("ATLAS_DEMO_MODE", "").lower() in ("1", "true", "yes")


# Human-readable message returned in the 503 body. Frontend renders it in a
# toast so users see why the action was rejected without dropping to console.
DEMO_BLOCKED_MESSAGE = (
    "This action is disabled in the public demo (it would consume LLM or "
    "Google Maps API quota). The full feature is available in a local "
    "checkout — see the README for setup."
)


def demo_block() -> None:
    """FastAPI dependency. 503s the request when ATLAS_DEMO_MODE is on.

    Use on endpoints that cost money or external API quota. Add to a route
    via `dependencies=[Depends(demo_block)]` or by mixing into the existing
    auth dependency tuple:

        @router.post(
            "/extract-departments",
            dependencies=[Depends(demo_block)],
        )
        async def extract_departments(...): ...

    Returns None on the open path; raises HTTPException(503) when blocked.
    The 503 (Service Unavailable) is more accurate than 403 here — the
    feature exists, it's just turned off for this deployment.
    """
    if is_demo_mode():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=DEMO_BLOCKED_MESSAGE,
        )
