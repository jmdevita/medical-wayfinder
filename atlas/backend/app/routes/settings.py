"""
Workspace-level diagnostics. Today: a single test-connection endpoint that
pings an OpenAI-compatible chat completions endpoint with a 2-token request,
so the dashboard can show a green/red dot per configured model.

When user-managed key storage lands, this is also where rotate-key flows go.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth import CurrentUser, require_facility_editor
from app.demo_mode import is_demo_mode
from app.rate_limits import limit_for
from app.services._io import ensure_tools_on_path
from app.services.url_safety import is_safe_external_url

router = APIRouter(prefix="/settings", tags=["settings"])


class TestConnectionRequest(BaseModel):
    base_url: str | None = Field(default=None, description="Override OPENAI_BASE_URL from env")
    model: str | None = Field(default=None, description="Override OPENAI_MODEL from env")
    timeout_s: float = Field(default=30.0, ge=1.0, le=30.0)


class TestConnectionResponse(BaseModel):
    ok: bool
    base_url: str
    model: str
    latency_ms: int | None = None
    sample: str | None = None
    error: str | None = None


@router.post("/test-connection", response_model=TestConnectionResponse)
@limit_for("test_connection")
async def test_connection(
    request: Request,
    response: Response,
    req: TestConnectionRequest,
    user: CurrentUser = Depends(require_facility_editor),
) -> TestConnectionResponse:
    _ = user
    _ = request
    _ = response  # injected so slowapi can stamp rate-limit headers
    """
    Try a 2-token chat completion against the configured (or supplied) endpoint.
    Used by the Settings view's "Test connection" button.
    """
    # Pull defaults from training/.env via the existing helper.
    ensure_tools_on_path()
    import fetch_departments_for_facility as fd  # type: ignore
    env = fd.load_env()

    base_url = (req.base_url or env.get("OPENAI_BASE_URL", "http://localhost:11434/v1")).rstrip("/")
    model    = req.model    or env.get("OPENAI_MODEL", "gemma4-31b")
    api_key  = env.get("OPENAI_API_KEY", "sk-NONE")

    # SSRF guard — applies to any user-supplied base_url. Skip for the in-repo
    # default if it points at a private host (the user's local llama-swap is
    # legitimate, so we only guard when the caller passed an override).
    if req.base_url is not None:
        ok, reason = is_safe_external_url(base_url)
        if not ok:
            raise HTTPException(status_code=400, detail=f"base_url rejected: {reason}")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 2,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=req.timeout_s) as client:
            r = await client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        latency_ms = int((time.monotonic() - started) * 1000)
        if r.status_code != 200:
            return TestConnectionResponse(
                ok=False,
                base_url=base_url,
                model=model,
                latency_ms=latency_ms,
                error=f"HTTP {r.status_code}: {r.text[:200]}",
            )
        body: dict[str, Any] = r.json()
        choice = (body.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        return TestConnectionResponse(
            ok=True,
            base_url=base_url,
            model=model,
            latency_ms=latency_ms,
            sample=content.strip()[:60] or None,
        )
    except httpx.ConnectError as exc:
        return TestConnectionResponse(
            ok=False, base_url=base_url, model=model,
            error=f"Connection refused: {exc}",
        )
    except httpx.TimeoutException:
        return TestConnectionResponse(
            ok=False, base_url=base_url, model=model,
            error=f"Timed out after {req.timeout_s}s",
        )
    except Exception as exc:  # noqa: BLE001
        return TestConnectionResponse(
            ok=False, base_url=base_url, model=model,
            error=f"{type(exc).__name__}: {exc}",
        )


class CurrentSettingsResponse(BaseModel):
    """Snapshot of what the backend is currently configured with — surfaced
    in Settings view so users see the real state, not hardcoded mockup text."""
    base_url: str
    model: str
    cors_origins: list[str]
    facilities_dir: str
    bootstrap_dir: str
    demo_mode: bool


@router.get("/current", response_model=CurrentSettingsResponse)
def current() -> CurrentSettingsResponse:
    from app.paths import BOOTSTRAP_DIR, FACILITIES_DIR
    ensure_tools_on_path()
    import fetch_departments_for_facility as fd  # type: ignore
    env = fd.load_env()
    cors = os.environ.get(
        "ATLAS_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173",
    )
    return CurrentSettingsResponse(
        base_url=env.get("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        model=env.get("OPENAI_MODEL", "gemma4-31b"),
        cors_origins=[o.strip() for o in cors.split(",") if o.strip()],
        facilities_dir=str(FACILITIES_DIR),
        bootstrap_dir=str(BOOTSTRAP_DIR),
        demo_mode=is_demo_mode(),
    )
