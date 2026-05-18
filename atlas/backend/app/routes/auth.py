"""
Auth routes:

  GET  /auth/login     redirect to GitHub OAuth (records state + return-to in session)
  GET  /auth/callback  GitHub redirects here; we verify state, exchange code, set session
  POST /auth/logout    clears the session cookie
  GET  /auth/me        returns the current user (or auth_enforced=false in dev)

Designed so the frontend never has to know what's going on — it just hits
`/api/auth/me`, redirects to `/api/auth/login` on 401, and trusts cookies.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from typing import Literal

from app import auth as auth_mod

router = APIRouter(prefix="/auth", tags=["auth"])


class WhoAmI(BaseModel):
    login: str | None
    auth_enforced: bool
    authenticated: bool
    role: Literal["viewer", "contributor", "facility_editor", "admin"]


@router.get("/me", response_model=WhoAmI)
def me(request: Request) -> WhoAmI:
    user = auth_mod.current_user_optional(request)
    return WhoAmI(
        login=user.login if user else None,
        auth_enforced=auth_mod.SETTINGS.enabled,
        authenticated=user is not None and user.auth_enforced,
        role=user.role if user else "viewer",
    )


@router.get("/login")
def login(request: Request, return_to: str = "/") -> RedirectResponse:
    safe_return_to = return_to if auth_mod.is_safe_return_to(return_to) else "/"
    if not auth_mod.SETTINGS.enabled:
        # Auth is off — there's nothing to log into. Bounce to the validated path.
        return RedirectResponse(url=safe_return_to, status_code=status.HTTP_302_FOUND)
    state = auth_mod.make_state()
    request.session["oauth_state"] = state
    request.session["oauth_return_to"] = safe_return_to
    return RedirectResponse(
        url=auth_mod.login_redirect_url(state),
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    if not auth_mod.SETTINGS.enabled:
        raise HTTPException(status_code=400, detail="Auth disabled")
    expected = request.session.pop("oauth_state", None)
    return_to = request.session.pop("oauth_return_to", "/") or "/"
    # Defense-in-depth: re-validate after pulling from session in case anything
    # ever bypasses the /login checks.
    if not auth_mod.is_safe_return_to(return_to):
        return_to = "/"
    if not code or not state or state != expected:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    login = await auth_mod.exchange_code_for_login(code)
    if not login:
        raise HTTPException(status_code=401, detail="GitHub authentication failed")
    # Any successful OAuth login is at least a contributor. The actual role
    # (admin / facility_editor / contributor) is resolved per-request from
    # the roles config — no allowlist check at the session boundary.
    request.session["login"] = login
    return RedirectResponse(url=return_to, status_code=status.HTTP_302_FOUND)


@router.post("/logout")
def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"status": "logged_out"}
