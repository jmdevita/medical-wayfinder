"""Tests for the streetview-edges routes + sidecar service.

The bulk Job and the per-edge regenerate path go through external systems
(Google Maps + the LLM endpoint), so we patch the helpers in
`app.services.streetview_edges` to stay hermetic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def published_with_edges(workspace: Path) -> str:
    """Seed a published facility with two edges:
      - one human-authored (shouldn't be touched by bulk fill)
      - one TODO stub (eligible for streetview suggestions)
    """
    slug = "kaiser_test"
    facilities_dir = workspace / "facilities"
    (facilities_dir / f"{slug}.json").write_text(
        json.dumps({
            "id": slug, "name": "Kaiser Test", "address": "123 Main St",
            "type": "hospital", "departments": [], "buildings": [], "parking": [],
        }, indent=2)
    )
    (facilities_dir / f"{slug}.topology.json").write_text(json.dumps({
        "facility_id": slug, "version": "1.0",
        "nodes": [
            {"id": "parking_a", "type": "parking", "label": "Parking A", "lat": 34.22, "lng": -118.43},
            {"id": "entrance_b", "type": "entrance", "label": "Entrance B", "lat": 34.221, "lng": -118.431},
            {"id": "entrance_c", "type": "entrance", "label": "Entrance C", "lat": 34.222, "lng": -118.432},
        ],
        "edges": [
            {"from": "parking_a", "to": "entrance_b", "distance_meters": 100,
             "walk_minutes": 1.5,
             "instruction": "Walk under the awning into Entrance B.",
             "blocked": False},
            {"from": "parking_a", "to": "entrance_c", "distance_meters": 120,
             "walk_minutes": 1.8,
             "instruction": "TODO: describe walking from Parking A to Entrance C.",
             "blocked": False},
        ],
    }, indent=2))
    return slug


def _editor(client_factory):
    return client_factory(login="editor-user", role="facility_editor")


def _viewer(client_factory):
    return client_factory(login="contributor-user", role="contributor")


# --- GET suggestions ------------------------------------------------------

def test_get_suggestions_empty_when_no_sidecar(client_factory, published_with_edges):
    c = _editor(client_factory)
    r = c.get(f"/api/streetview-edges/{published_with_edges}/suggestions")
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == published_with_edges
    assert body["suggestions"] == []


def test_get_suggestions_requires_facility_editor(client_factory, published_with_edges):
    contrib = _viewer(client_factory)
    r = contrib.get(f"/api/streetview-edges/{published_with_edges}/suggestions")
    assert r.status_code == 401


def test_get_suggestions_404_when_unknown_slug(client_factory, workspace):
    c = _editor(client_factory)
    r = c.get("/api/streetview-edges/no_such_facility/suggestions")
    assert r.status_code == 404


# --- DELETE discard -------------------------------------------------------

def test_discard_removes_entry(client_factory, published_with_edges, workspace):
    from app.services.streetview_edges import save_suggestions
    save_suggestions(published_with_edges, {
        "slug": published_with_edges,
        "generated_at": "2026-04-28T00:00:00Z",
        "suggestions": [
            {"from": "parking_a", "to": "entrance_c",
             "instruction": "Walk past the trees.", "landmarks": [],
             "routing": {"method": "straight_line", "routed_m": None, "polyline_points": None},
             "coverage": {"verdict": "warn", "metrics": {}, "reasons": []},
             "evidence": {"pano_ids": ["abc"], "pano_dates": ["2024-01"], "model": "gemma4-31b"},
             "generated_at": "2026-04-28T00:00:00Z"},
        ],
    })
    c = _editor(client_factory)
    r = c.delete(f"/api/streetview-edges/{published_with_edges}/suggestions/parking_a/entrance_c")
    assert r.status_code == 200
    assert r.json()["remaining"] == 0


def test_discard_noop_when_missing(client_factory, published_with_edges):
    c = _editor(client_factory)
    r = c.delete(f"/api/streetview-edges/{published_with_edges}/suggestions/parking_a/entrance_c")
    assert r.status_code == 200
    assert r.json()["remaining"] == 0


# --- POST accept ----------------------------------------------------------

def test_accept_replaces_topology_instruction(client_factory, published_with_edges, workspace):
    from app.services.streetview_edges import save_suggestions
    save_suggestions(published_with_edges, {
        "slug": published_with_edges,
        "generated_at": "2026-04-28T00:00:00Z",
        "suggestions": [{
            "from": "parking_a", "to": "entrance_c",
            "instruction": "Walk past the white building marked \"3\".",
            "landmarks": ["the white building marked \"3\""],
            "routing": {"method": "osm_footway", "routed_m": 130, "polyline_points": 22},
            "coverage": {"verdict": "warn", "metrics": {}, "reasons": []},
            "evidence": {"pano_ids": ["abc"], "pano_dates": ["2024-01"], "model": "gemma4-31b"},
            "generated_at": "2026-04-28T00:00:00Z",
        }],
    })

    c = _editor(client_factory)
    r = c.post(
        f"/api/streetview-edges/{published_with_edges}/accept",
        json={"from_id": "parking_a", "to_id": "entrance_c"},
    )
    assert r.status_code == 200, r.text
    assert "Walk past the white building" in r.json()["instruction"]

    # Topology should now have the new instruction.
    topo_path = workspace / "facilities" / f"{published_with_edges}.topology.json"
    topology = json.loads(topo_path.read_text())
    edge = next(e for e in topology["edges"] if e["from"] == "parking_a" and e["to"] == "entrance_c")
    assert "white building" in edge["instruction"]
    assert not edge["instruction"].startswith("TODO:")

    # Sidecar should no longer contain that suggestion.
    sidecar_path = workspace / "bootstrap" / published_with_edges / "suggestions.json"
    if sidecar_path.exists():
        sidecar = json.loads(sidecar_path.read_text())
        assert sidecar["suggestions"] == []


def test_accept_404_when_no_suggestion(client_factory, published_with_edges):
    c = _editor(client_factory)
    r = c.post(
        f"/api/streetview-edges/{published_with_edges}/accept",
        json={"from_id": "parking_a", "to_id": "entrance_c"},
    )
    assert r.status_code == 404


def test_accept_409_when_skipped_no_coverage(client_factory, published_with_edges):
    from app.services.streetview_edges import save_suggestions
    save_suggestions(published_with_edges, {
        "slug": published_with_edges,
        "generated_at": "2026-04-28T00:00:00Z",
        "suggestions": [{
            "from": "parking_a", "to": "entrance_c",
            "instruction": None, "landmarks": [],
            "routing": {"method": "straight_line", "routed_m": None, "polyline_points": None},
            "coverage": {"verdict": "fail", "metrics": {}, "reasons": ["max snap too high"]},
            "evidence": {"pano_ids": [], "pano_dates": [], "model": None},
            "skipped_reason": "coverage_fail",
            "generated_at": "2026-04-28T00:00:00Z",
        }],
    })
    c = _editor(client_factory)
    r = c.post(
        f"/api/streetview-edges/{published_with_edges}/accept",
        json={"from_id": "parking_a", "to_id": "entrance_c"},
    )
    assert r.status_code == 409


# --- Auth gates -----------------------------------------------------------

def test_accept_requires_facility_editor(client_factory, published_with_edges):
    contrib = _viewer(client_factory)
    r = contrib.post(
        f"/api/streetview-edges/{published_with_edges}/accept",
        json={"from_id": "parking_a", "to_id": "entrance_c"},
    )
    assert r.status_code == 401


def test_pano_proxy_requires_facility_editor(client_factory, published_with_edges):
    contrib = _viewer(client_factory)
    r = contrib.get(
        f"/api/streetview-edges/{published_with_edges}/panos/abc1234567.jpg"
    )
    assert r.status_code == 401


def test_pano_proxy_503_without_api_key(client_factory, published_with_edges,
                                        monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    c = _editor(client_factory)
    r = c.get(
        f"/api/streetview-edges/{published_with_edges}/panos/abc1234567.jpg"
    )
    assert r.status_code == 503


def test_pano_proxy_rejects_oversize_size(client_factory, published_with_edges,
                                           monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    c = _editor(client_factory)
    r = c.get(
        f"/api/streetview-edges/{published_with_edges}/panos/abc1234567.jpg",
        params={"size": "9999x9999"},
    )
    assert r.status_code == 422


def test_pano_proxy_rejects_invalid_pano_id(client_factory, published_with_edges,
                                             monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    c = _editor(client_factory)
    r = c.get(
        f"/api/streetview-edges/{published_with_edges}/panos/short.jpg"
    )
    assert r.status_code == 422


# --- Eligibility (pure unit) ----------------------------------------------

def test_eligibility_rejects_human_prose(workspace, published_with_edges):
    from app.services.streetview_edges import _eligible
    assert _eligible({"instruction": ""}) is True
    assert _eligible({"instruction": "TODO: describe..."}) is True
    assert _eligible({"instruction": "Walk through the door."}) is False
    assert _eligible({}) is True  # Missing field counts as empty.


# --- Security: API key scrubbing ------------------------------------------

def test_scrub_secrets_redacts_key_param(workspace):
    from app.services.streetview_edges import scrub_secrets
    leaked = "Failed: https://maps.googleapis.com/foo?pano=abc&key=AIzaSy_REAL_KEY&fov=90"
    out = scrub_secrets(leaked)
    assert "AIzaSy_REAL_KEY" not in out
    assert "key=REDACTED" in out
    # Other params untouched
    assert "pano=abc" in out and "fov=90" in out


def test_scrub_secrets_redacts_api_key_alias(workspace):
    from app.services.streetview_edges import scrub_secrets
    out = scrub_secrets("oops https://example.com/x?api_key=SECRET&y=1")
    assert "SECRET" not in out
    assert "api_key=REDACTED" in out


def test_scrub_secrets_handles_empty_and_no_match(workspace):
    from app.services.streetview_edges import scrub_secrets
    assert scrub_secrets("") == ""
    assert scrub_secrets("nothing to scrub here") == "nothing to scrub here"


def test_pano_proxy_invalid_fov_rejected(client_factory, published_with_edges,
                                         monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    c = _editor(client_factory)
    r = c.get(
        f"/api/streetview-edges/{published_with_edges}/panos/abc1234567.jpg",
        params={"fov": 999},
    )
    assert r.status_code == 422


def test_pano_proxy_invalid_pitch_rejected(client_factory, published_with_edges,
                                           monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    c = _editor(client_factory)
    r = c.get(
        f"/api/streetview-edges/{published_with_edges}/panos/abc1234567.jpg",
        params={"pitch": 200},
    )
    assert r.status_code == 422


def test_pano_proxy_path_traversal_blocked(client_factory, published_with_edges,
                                           monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    c = _editor(client_factory)
    # Slug with .. or / would change file lookups; pano_id with . or /
    # would be path traversal.
    r = c.get(f"/api/streetview-edges/{published_with_edges}/panos/..%2Fevil.jpg")
    # FastAPI either 404s or matches a different route; either way the
    # validation regex rejects it.
    assert r.status_code in (404, 422)


def test_accept_blocked_by_lock_held_by_other(client_factory, published_with_edges,
                                              monkeypatch: pytest.MonkeyPatch):
    """When another editor holds the slug's lock, accept must 423 like PUT
    /facilities/{slug}/topology."""
    monkeypatch.setenv("ATLAS_AUTH_ENABLED", "true")
    from app.services.streetview_edges import save_suggestions
    from app.locks import locks
    save_suggestions(published_with_edges, {
        "slug": published_with_edges,
        "generated_at": "2026-04-28T00:00:00Z",
        "suggestions": [{
            "from": "parking_a", "to": "entrance_c",
            "instruction": "Walk past the white building.",
            "landmarks": [],
            "routing": {"method": "straight_line", "routed_m": None, "polyline_points": None},
            "coverage": {"verdict": "warn", "metrics": {}, "reasons": []},
            "evidence": {"pano_ids": [], "pano_dates": [], "model": "gemma4-31b"},
            "generated_at": "2026-04-28T00:00:00Z",
        }],
    })

    locks.acquire_or_heartbeat(published_with_edges, "another-editor")
    try:
        c = _editor(client_factory)
        r = c.post(
            f"/api/streetview-edges/{published_with_edges}/accept",
            json={"from_id": "parking_a", "to_id": "entrance_c"},
        )
        assert r.status_code == 423
    finally:
        locks.release(published_with_edges, "another-editor")
