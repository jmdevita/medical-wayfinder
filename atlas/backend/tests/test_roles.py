"""Roles config loading + role resolution.

Pure unit tests — no FastAPI involved. The fixtures rebuild the auth module
from a fresh env so each test sees its own roles.yaml.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def test_roles_yaml_round_trip(workspace: Path):
    from app.auth import Roles

    roles = Roles.load()
    assert roles.admin == "admin-user"
    assert roles.facility_editors == frozenset({"editor-user"})


def test_role_for_resolution(workspace: Path):
    from app.auth import Roles

    roles = Roles.load()
    assert roles.role_for(None) == "viewer"
    assert roles.role_for("") == "viewer"
    assert roles.role_for("admin-user") == "admin"
    assert roles.role_for("ADMIN-USER") == "admin"  # case-insensitive
    assert roles.role_for("editor-user") == "facility_editor"
    assert roles.role_for("random-stranger") == "contributor"


def test_reload_picks_up_changes(workspace: Path):
    from app.auth import ROLES

    roles_file = workspace / "roles.yaml"
    roles_file.write_text(
        yaml.safe_dump({"admin": "admin-user", "facility_editors": ["new-editor"]})
    )
    ROLES.reload()
    assert "new-editor" in ROLES.facility_editors


def test_dev_mode_user_is_admin(tmp_path: Path, monkeypatch):
    """When ATLAS_AUTH_ENABLED is off, the bypass user gets admin role so
    local end-to-end stays fully functional."""
    monkeypatch.setenv("ATLAS_AUTH_ENABLED", "")
    monkeypatch.delenv("ATLAS_ROLES_FILE", raising=False)

    import importlib
    import sys

    for name in list(sys.modules):
        if name.startswith("app"):
            sys.modules.pop(name)
    auth = importlib.import_module("app.auth")

    # Use a synthetic Request with no session so _resolve_user falls through.
    class FakeRequest:
        session: dict = {}

    user = auth._resolve_user(FakeRequest())  # type: ignore[arg-type]
    assert user is not None
    assert user.login == "dev"
    assert user.role == "admin"
    assert user.auth_enforced is False
