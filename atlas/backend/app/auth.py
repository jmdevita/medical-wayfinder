"""
GitHub OAuth + signed-cookie session for the Atlas dashboard.

Auth has four tiers, defined in `atlas/data/roles.yaml`:

  viewer            Anyone (no login). Can read published facilities only.
  contributor       Any logged-in GitHub user. Can fork a published facility
                    into a personal draft and submit it for review.
  facility_editor   Listed in `roles.yaml`. Can edit the shared bootstrap
                    workspace, run LLM jobs, and bootstrap new facilities.
  admin             Single login in `roles.yaml`. Only role that can publish
                    or approve a proposal.

Auth is *opt-in* via `ATLAS_AUTH_ENABLED=true`. When disabled (the default),
the dependencies treat the request as the dev user with **admin** role so the
local end-to-end experience stays unchanged.

Configuration env vars:

  ATLAS_AUTH_ENABLED              "true" to enforce; anything else means off.
  ATLAS_GITHUB_OAUTH_CLIENT_ID    From github.com/settings/developers.
  ATLAS_GITHUB_OAUTH_CLIENT_SECRET
  ATLAS_ROLES_FILE                Path to the YAML tier config (default:
                                  atlas/data/roles.yaml).
  ATLAS_SESSION_SECRET            Random 32+ byte string. Required when on.
  ATLAS_PUBLIC_URL                e.g. https://atlas.example.com — used for
                                  the OAuth redirect URI. Defaults to
                                  http://localhost:8000 for local testing.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
import yaml
from fastapi import HTTPException, Request, status
from starlette.middleware.sessions import SessionMiddleware

from app.paths import ROLES_FILE

log = logging.getLogger("atlas.auth")

Role = Literal["viewer", "contributor", "facility_editor", "admin"]


@dataclass(frozen=True)
class AuthSettings:
    enabled: bool
    client_id: str
    client_secret: str
    session_secret: str
    public_url: str

    @classmethod
    def from_env(cls) -> "AuthSettings":
        enabled = os.environ.get("ATLAS_AUTH_ENABLED", "").lower() in ("1", "true", "yes")
        client_id     = os.environ.get("ATLAS_GITHUB_OAUTH_CLIENT_ID", "")
        client_secret = os.environ.get("ATLAS_GITHUB_OAUTH_CLIENT_SECRET", "")
        session_secret = os.environ.get("ATLAS_SESSION_SECRET", "")
        public_url = os.environ.get("ATLAS_PUBLIC_URL", "http://localhost:8000").rstrip("/")
        return cls(
            enabled=enabled,
            client_id=client_id,
            client_secret=client_secret,
            session_secret=session_secret,
            public_url=public_url,
        )

    def assert_runnable(self) -> None:
        """Fail fast at startup if auth is enabled but misconfigured."""
        if not self.enabled:
            return
        missing = []
        if not self.client_id:     missing.append("ATLAS_GITHUB_OAUTH_CLIENT_ID")
        if not self.client_secret: missing.append("ATLAS_GITHUB_OAUTH_CLIENT_SECRET")
        if not self.session_secret or len(self.session_secret) < 32:
            missing.append("ATLAS_SESSION_SECRET (≥32 chars)")
        # roles.yaml is the source of truth for who's allowed in;
        # ROLES.assert_runnable validates it.
        if not ROLES.admin and not ROLES.facility_editors:
            missing.append("roles.yaml (admin or facility_editors)")
        if missing:
            raise RuntimeError(
                "Auth is enabled but configuration is incomplete. Missing/invalid: "
                + ", ".join(missing)
            )


# ---------------------------------------------------------------------------
# Role config (atlas/data/roles.yaml)
# ---------------------------------------------------------------------------

@dataclass
class Roles:
    """Tier config loaded from `atlas/data/roles.yaml`. Mutable so the admin-
    only `/admin/roles/reload` endpoint can swap contents without a restart.
    Logins are stored lowercased for case-insensitive comparison."""

    admin: str = ""
    facility_editors: frozenset[str] = field(default_factory=frozenset)
    source_path: Path = field(default_factory=lambda: ROLES_FILE)

    @classmethod
    def load(cls, path: Path = ROLES_FILE) -> "Roles":
        admin = ""
        editors: set[str] = set()
        if path.exists():
            try:
                raw = yaml.safe_load(path.read_text()) or {}
            except yaml.YAMLError as exc:
                raise RuntimeError(f"roles.yaml is not valid YAML: {exc}") from exc
            if not isinstance(raw, dict):
                raise RuntimeError("roles.yaml must be a mapping at the top level.")
            admin_raw = raw.get("admin", "") or ""
            if not isinstance(admin_raw, str):
                raise RuntimeError("roles.yaml `admin` must be a single GitHub login string.")
            admin = admin_raw.strip().lower()
            editors_raw = raw.get("facility_editors") or []
            if not isinstance(editors_raw, list):
                raise RuntimeError("roles.yaml `facility_editors` must be a list.")
            for entry in editors_raw:
                if not isinstance(entry, str):
                    continue
                stripped = entry.strip().lower()
                if stripped:
                    editors.add(stripped)
        return cls(admin=admin, facility_editors=frozenset(editors), source_path=path)

    def role_for(self, login: str | None) -> Role:
        """Resolve a login to its role. Unauthenticated → viewer. Unknown
        authenticated logins → contributor."""
        if not login:
            return "viewer"
        low = login.strip().lower()
        if not low:
            return "viewer"
        if self.admin and low == self.admin:
            return "admin"
        if low in self.facility_editors:
            return "facility_editor"
        return "contributor"

    def reload(self) -> None:
        fresh = Roles.load(self.source_path)
        self.admin = fresh.admin
        self.facility_editors = fresh.facility_editors


SETTINGS = AuthSettings.from_env()
ROLES = Roles.load()


def install_session_middleware(app: Any) -> None:
    """Mount the cookie-session middleware iff auth is on. We use a
    non-trivial fallback secret in dev so cookie-state survives reloads
    without forcing every dev to set the env var."""
    secret = SETTINGS.session_secret or "atlas-dev-only-do-not-use-in-prod"
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie="atlas_sess",
        max_age=14 * 24 * 60 * 60,  # 14 days
        same_site="lax",
        https_only=SETTINGS.public_url.startswith("https://"),
    )


# ---------------------------------------------------------------------------
# OAuth dance
# ---------------------------------------------------------------------------

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN     = "https://github.com/login/oauth/access_token"
GITHUB_USER      = "https://api.github.com/user"


def login_redirect_url(state: str) -> str:
    """
    Build the GitHub authorize URL. Caller stores `state` and `return_to` in
    the session before redirecting so we can verify the callback and bounce
    the user back where they came from.
    """
    params = {
        "client_id": SETTINGS.client_id,
        "redirect_uri": f"{SETTINGS.public_url}/api/auth/callback",
        "scope": "read:user",
        "state": state,
        # Intentionally not asking for `user:email` — we only need login.
    }
    return f"{GITHUB_AUTHORIZE}?{urlencode(params)}"


def is_safe_return_to(target: str) -> bool:
    """
    Reject anything that isn't a same-origin relative path. `//evil.com` and
    `/\\evil.com` are the classic open-redirect tricks; both fail this check.
    """
    if not target.startswith("/"):
        return False
    if target.startswith("//") or target.startswith("/\\"):
        return False
    return True


async def exchange_code_for_login(code: str) -> str | None:
    """
    Trade the OAuth code for a token, fetch the user, return the login string
    or None on failure. Logs but doesn't expose specific GitHub errors so
    auth probes don't double as GitHub fingerprinting.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            t = await client.post(
                GITHUB_TOKEN,
                data={
                    "client_id": SETTINGS.client_id,
                    "client_secret": SETTINGS.client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json"},
            )
        except httpx.RequestError as exc:
            log.warning("auth_token_exchange_failed", extra={"error": str(exc)})
            return None
        if t.status_code != 200:
            log.warning("auth_token_exchange_status", extra={"status": t.status_code})
            return None
        token = t.json().get("access_token")
        if not token:
            return None
        try:
            u = await client.get(
                GITHUB_USER,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        except httpx.RequestError as exc:
            log.warning("auth_user_fetch_failed", extra={"error": str(exc)})
            return None
        if u.status_code != 200:
            return None
        login = u.json().get("login")
        return login.lower() if isinstance(login, str) else None


def make_state() -> str:
    return secrets.token_urlsafe(24)


# ---------------------------------------------------------------------------
# Dependency for protected routes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CurrentUser:
    login: str          # GitHub login, lowercased ("dev" in bypass mode)
    auth_enforced: bool # True if auth is on; False means dev bypass
    role: Role          # viewer | contributor | facility_editor | admin


_ROLE_RANK: dict[Role, int] = {
    "viewer": 0,
    "contributor": 1,
    "facility_editor": 2,
    "admin": 3,
}


def _resolve_user(request: Request) -> CurrentUser | None:
    """Return the CurrentUser for this request, or None if unauthenticated.
    In dev mode the bypass user is treated as admin so local end-to-end works."""
    if not SETTINGS.enabled:
        return CurrentUser(login="dev", auth_enforced=False, role="admin")
    login = request.session.get("login") if hasattr(request, "session") else None
    if not isinstance(login, str) or not login:
        return None
    role = ROLES.role_for(login)
    # Authenticated-but-unrecognized logins are contributors. The session was
    # only set after a successful OAuth callback so the login string itself is
    # trustworthy; the role just falls through to the lowest authenticated tier.
    return CurrentUser(login=login, auth_enforced=True, role=role)


def _at_least(user: CurrentUser | None, minimum: Role) -> CurrentUser:
    if user is None or _ROLE_RANK[user.role] < _ROLE_RANK[minimum]:
        # 401 keeps the existing frontend redirect-to-login behavior intact;
        # 403 would be technically more accurate when an authenticated user
        # lacks the role, but the cost is breaking the redirect.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in with GitHub.",
            headers={"WWW-Authenticate": 'Cookie realm="atlas"'},
        )
    return user


def require_authenticated(request: Request) -> CurrentUser:
    """Any logged-in GitHub user. Used by contributor-tier endpoints
    (fork, edit personal draft, submit proposal)."""
    return _at_least(_resolve_user(request), "contributor")


def require_facility_editor(request: Request) -> CurrentUser:
    """facility_editor or admin. Used by shared-workspace mutations,
    LLM jobs, and bootstrap."""
    return _at_least(_resolve_user(request), "facility_editor")


def require_admin(request: Request) -> CurrentUser:
    """Admin only. Used by publish, approve/reject, and roles reload."""
    return _at_least(_resolve_user(request), "admin")


def current_user_optional(request: Request) -> CurrentUser | None:
    """Returns the CurrentUser if authenticated (or dev), else None. Used by
    `/auth/me` so the frontend can render its sign-in state without a 401."""
    return _resolve_user(request)
