"""
Rate limiting via slowapi. Opt-in via ATLAS_RATE_LIMIT_ENABLED=true; off by
default so local dev isn't surprised by 429s.

The limit key prefers the authenticated user's GitHub login (so per-user
quotas survive NAT'd IPs); falls back to the remote IP when auth is off or
the user isn't signed in.

Adjust ceilings via env (`ATLAS_RATE_LIMIT_*`) without redeploying code.
"""

from __future__ import annotations

import os
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def _enabled() -> bool:
    return os.environ.get("ATLAS_RATE_LIMIT_ENABLED", "").lower() in ("1", "true", "yes")


def _key(request: Request) -> str:
    # Prefer the signed-in user when present so a single user behind a shared
    # IP isn't punished for a coworker's traffic, and so different users
    # behind the same NAT have independent buckets.
    sess = getattr(request, "session", None)
    login = sess.get("login") if isinstance(sess, dict) else None
    if isinstance(login, str) and login:
        return f"user:{login}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=_key,
    default_limits=[],
    enabled=_enabled(),
    headers_enabled=True,  # add X-RateLimit-* headers so clients can self-throttle
)


def _env_limit(var: str, default: str) -> str:
    return os.environ.get(var, default)


# Per-route limits, looked up by the route function name. Centralised so we
# can tune from one place. Keys are also exported for tests.
LIMITS: dict[str, list[str]] = {
    # OSM bootstrap hits external services (Nominatim + Overpass).
    "bootstrap": [
        _env_limit("ATLAS_RATE_LIMIT_BOOTSTRAP_MIN", "3/minute"),
        _env_limit("ATLAS_RATE_LIMIT_BOOTSTRAP_DAY", "30/day"),
    ],
    # LLM jobs cost real money / quota.
    "extract_departments": [
        _env_limit("ATLAS_RATE_LIMIT_EXTRACT_MIN", "5/minute"),
        _env_limit("ATLAS_RATE_LIMIT_EXTRACT_DAY", "50/day"),
    ],
    "expand_aliases": [
        _env_limit("ATLAS_RATE_LIMIT_ALIASES_MIN", "5/minute"),
        _env_limit("ATLAS_RATE_LIMIT_ALIASES_DAY", "50/day"),
    ],
    # Cheap but mutating — kept generous.
    "draft_edges":   [_env_limit("ATLAS_RATE_LIMIT_DRAFT_MIN",   "20/minute")],
    # Street View edge-walker — bulk run is heavy (LLM + 200+ Google calls).
    # Per-edge regenerate and pano proxy are smaller but each hits Google.
    "streetview_edges_bulk": [
        _env_limit("ATLAS_RATE_LIMIT_SV_BULK_MIN",  "2/minute"),
        _env_limit("ATLAS_RATE_LIMIT_SV_BULK_DAY",  "20/day"),
    ],
    "streetview_edges_regenerate": [
        _env_limit("ATLAS_RATE_LIMIT_SV_REGEN_MIN", "10/minute"),
        _env_limit("ATLAS_RATE_LIMIT_SV_REGEN_DAY", "300/day"),
    ],
    "streetview_edges_pano": [
        _env_limit("ATLAS_RATE_LIMIT_SV_PANO_MIN",  "120/minute"),
        _env_limit("ATLAS_RATE_LIMIT_SV_PANO_DAY",  "5000/day"),
    ],
    # Photo edge-walker — uploads write disk + parse EXIF; generate hits the
    # vision LLM; photo proxy serves persisted JPEGs from disk.
    "photo_edges_upload": [
        _env_limit("ATLAS_RATE_LIMIT_PHOTO_UPLOAD_MIN", "30/minute"),
        _env_limit("ATLAS_RATE_LIMIT_PHOTO_UPLOAD_DAY", "500/day"),
    ],
    "photo_edges_generate": [
        _env_limit("ATLAS_RATE_LIMIT_PHOTO_GEN_MIN", "10/minute"),
        _env_limit("ATLAS_RATE_LIMIT_PHOTO_GEN_DAY", "200/day"),
    ],
    "photo_edges_photo": [
        _env_limit("ATLAS_RATE_LIMIT_PHOTO_PROXY_MIN", "300/minute"),
        _env_limit("ATLAS_RATE_LIMIT_PHOTO_PROXY_DAY", "10000/day"),
    ],
    "save_topology": [_env_limit("ATLAS_RATE_LIMIT_SAVE_MIN",    "60/minute")],
    "save_departments": [_env_limit("ATLAS_RATE_LIMIT_SAVE_MIN",  "60/minute")],
    "save_metadata":    [_env_limit("ATLAS_RATE_LIMIT_SAVE_MIN",  "60/minute")],
    "publish":       [_env_limit("ATLAS_RATE_LIMIT_PUBLISH_MIN", "10/minute")],
    "reroute_edges": [_env_limit("ATLAS_RATE_LIMIT_REROUTE_MIN", "30/minute")],
    "test_connection": [_env_limit("ATLAS_RATE_LIMIT_TEST_MIN", "10/minute")],
}


def install_rate_limit_handler(app: FastAPI) -> None:
    """Wire the global 429 handler so callers see consistent JSON, not text."""
    app.state.limiter = limiter

    async def handler(request: Request, exc: Exception):
        # slowapi raises RateLimitExceeded; the type guard keeps mypy quiet.
        retry_after = None
        if isinstance(exc, RateLimitExceeded):
            retry_after = getattr(exc, "retry_after", None)
        body: dict[str, object] = {
            "detail": "Rate limit exceeded. Slow down or wait a minute.",
        }
        if retry_after is not None:
            body["retry_after_seconds"] = retry_after
        headers = {"Retry-After": str(retry_after)} if retry_after else {}
        return JSONResponse(status_code=429, content=body, headers=headers)

    app.add_exception_handler(RateLimitExceeded, handler)


def limit_for(route_name: str) -> Callable:
    """Apply limits[route_name] (if any) as a slowapi decorator. No-op when
    rate limiting is disabled or the route has no configured limits."""
    limits = LIMITS.get(route_name, [])
    if not limits or not _enabled():
        # Returning a no-op decorator keeps call sites free of conditionals.
        def noop(fn: Callable) -> Callable:
            return fn
        return noop
    spec = "; ".join(limits)
    return limiter.limit(spec)
