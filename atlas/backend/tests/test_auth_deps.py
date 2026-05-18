"""Per-role dependency gating across the route surface.

Each role-tier dep should accept its own role and everything above, and 401
everything below. Tests are integration-style via TestClient with overrides.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _publish_response(client: TestClient, slug: str):
    return client.post(f"/api/facilities/{slug}/publish", json={})


def test_publish_requires_admin(workspace, published_facility, client_factory):
    """Only admin can hit /publish. facility_editor and contributor 401."""
    contrib = client_factory(login="random", role="contributor")
    editor = client_factory(login="editor-user", role="facility_editor")
    admin = client_factory(login="admin-user", role="admin")

    # Publish a non-existent slug to avoid actually writing anything; we just
    # want to confirm the auth gate, not the publish logic.
    assert _publish_response(contrib, "ghost_slug").status_code == 401
    assert _publish_response(editor,  "ghost_slug").status_code == 401
    # Admin reaches the route; will 404 or 422 because no facility exists.
    assert _publish_response(admin, "ghost_slug").status_code in (404, 422)


def test_bootstrap_requires_facility_editor(workspace, client_factory):
    contrib = client_factory(login="random", role="contributor")
    editor = client_factory(login="editor-user", role="facility_editor")

    # Body shape comes from BootstrapRequest; minimal valid query.
    body = {"query": "test hospital", "include_landmarks": False}
    assert contrib.post("/api/bootstrap", json=body).status_code == 401
    # Editor passes auth; rate-limit/job machinery will produce 200 or 429.
    r = editor.post("/api/bootstrap", json=body)
    assert r.status_code != 401


def test_fork_requires_authenticated(workspace, published_facility, client_factory):
    """Any authenticated user can fork; viewer/anonymous gets 401."""
    contrib = client_factory(login="random", role="contributor")
    r = contrib.post(f"/api/facilities/{published_facility}/fork")
    assert r.status_code == 200
    assert r.json()["author"] == "random"


def test_anonymous_cannot_fork(workspace, published_facility, anon_client):
    r = anon_client.post(f"/api/facilities/{published_facility}/fork")
    assert r.status_code == 401


def test_proposals_list_admin_only(workspace, client_factory):
    contrib = client_factory(login="random", role="contributor")
    editor = client_factory(login="editor-user", role="facility_editor")
    admin = client_factory(login="admin-user", role="admin")

    assert contrib.get("/api/proposals").status_code == 401
    assert editor.get("/api/proposals").status_code == 401
    assert admin.get("/api/proposals").status_code == 200


def test_save_topology_requires_facility_editor(workspace, published_facility, client_factory):
    contrib = client_factory(login="random", role="contributor")
    editor = client_factory(login="editor-user", role="facility_editor")

    body = {"version": "1.0", "facility_id": published_facility, "nodes": [], "edges": []}
    assert contrib.put(f"/api/facilities/{published_facility}/topology", json=body).status_code == 401
    # Editor reaches the route; whatever status comes next isn't 401.
    r = editor.put(f"/api/facilities/{published_facility}/topology", json=body)
    assert r.status_code != 401
