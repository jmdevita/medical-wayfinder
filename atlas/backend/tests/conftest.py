"""Shared fixtures for the Atlas backend tests.

Each test gets fresh data dirs (FACILITIES_DIR, BOOTSTRAP_DIR, PROPOSALS_DIR)
and a TestClient with auth-related dependency overrides so we can simulate
each tier without going through the real GitHub OAuth flow.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Lay out a clean atlas/data/ tree in a tmp dir and point the backend at it.
    Imports the app fresh so module-level path constants pick up the env vars."""
    data = tmp_path / "data"
    facilities = data / "facilities"
    bootstrap = data / "bootstrap"
    proposals = data / "proposals"
    facilities.mkdir(parents=True)
    bootstrap.mkdir(parents=True)
    proposals.mkdir(parents=True)

    monkeypatch.setenv("ATLAS_FACILITIES_DIR", str(facilities))
    monkeypatch.setenv("ATLAS_BOOTSTRAP_DIR", str(bootstrap))
    monkeypatch.setenv("ATLAS_PROPOSALS_DIR", str(proposals))

    roles_file = data / "roles.yaml"
    roles_file.write_text(
        yaml.safe_dump(
            {"admin": "admin-user", "facility_editors": ["editor-user"]}
        )
    )
    monkeypatch.setenv("ATLAS_ROLES_FILE", str(roles_file))

    # Auth disabled; tests use dependency_overrides to mint specific roles.
    monkeypatch.setenv("ATLAS_AUTH_ENABLED", "")

    # Reset module state so the new env vars take effect.
    _reset_app_modules()
    return data


@pytest.fixture
def published_facility(workspace: Path) -> str:
    """Seed a minimal published facility (kaiser_test) so contributors have
    something to fork."""
    slug = "kaiser_test"
    facilities_dir = workspace / "facilities"
    (facilities_dir / f"{slug}.json").write_text(
        json.dumps(
            {
                "id": slug,
                "name": "Kaiser Test",
                "address": "123 Main St",
                "type": "hospital",
                "departments": [],
                "buildings": [],
                "parking": [],
            },
            indent=2,
        )
    )
    (facilities_dir / f"{slug}.topology.json").write_text(
        json.dumps({"facility_id": slug, "version": "1.0", "nodes": [], "edges": []}, indent=2)
    )
    return slug


@pytest.fixture
def client_factory(workspace: Path):
    """Build a TestClient that authenticates as a given login+role via test
    headers. Multiple clients coexist in the same test because each request
    carries its own headers — no global override state to clobber."""
    from fastapi import Header, HTTPException, status

    from app import auth as auth_mod
    from app.main import app

    _ROLE_RANK = {"viewer": 0, "contributor": 1, "facility_editor": 2, "admin": 3}

    def _gate_factory(minimum: str):
        def dep(
            x_test_login: str | None = Header(default=None),
            x_test_role: str | None = Header(default=None),
        ) -> auth_mod.CurrentUser:
            if (
                not x_test_login
                or x_test_role not in ("contributor", "facility_editor", "admin")
                or _ROLE_RANK[x_test_role] < _ROLE_RANK[minimum]
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="not authorized",
                )
            return auth_mod.CurrentUser(  # type: ignore[arg-type]
                login=x_test_login, auth_enforced=True, role=x_test_role
            )

        return dep

    app.dependency_overrides[auth_mod.require_authenticated] = _gate_factory("contributor")
    app.dependency_overrides[auth_mod.require_facility_editor] = _gate_factory("facility_editor")
    app.dependency_overrides[auth_mod.require_admin] = _gate_factory("admin")

    def _make(*, login: str, role: str) -> TestClient:
        client = TestClient(app)
        client.headers.update({"x-test-login": login, "x-test-role": role})
        return client

    yield _make
    app.dependency_overrides.clear()


@pytest.fixture
def anon_client(client_factory) -> TestClient:
    """A TestClient without auth headers — the override deps in client_factory
    treat missing headers as unauthenticated, so any role-gated call 401s."""
    # client_factory installs the overrides; we just use a plain TestClient
    # without the test-role headers.
    from app.main import app

    return TestClient(app)


def _raise_401():
    from fastapi import HTTPException, status

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authorized")


def _reset_app_modules() -> None:
    """Drop cached modules so each test rebuilds from the new env vars."""
    import sys

    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)
