"""End-to-end proposal lifecycle: fork → edit → submit → approve / reject.

Cross-user isolation is also covered: Alice cannot read/write Bob's draft."""

from __future__ import annotations


def _topology_body(slug: str, n: int):
    """Make a minimal valid topology with `n` nodes (no edges)."""
    return {
        "version": "1.0",
        "facility_id": slug,
        "nodes": [
            {"id": f"n{i}", "type": "landmark", "label": f"N{i}", "lat": 1.0, "lng": 2.0}
            for i in range(n)
        ],
        "edges": [],
    }


def test_fork_creates_personal_draft(workspace, published_facility, client_factory):
    contrib = client_factory(login="alice", role="contributor")
    r = contrib.post(f"/api/facilities/{published_facility}/fork")
    assert r.status_code == 200, r.json()
    draft = (workspace / "proposals" / "alice" / published_facility)
    assert (draft / "facility.json").exists()
    assert (draft / "topology.json").exists()


def test_fork_edit_submit_approve_happy_path(workspace, published_facility, client_factory):
    contrib = client_factory(login="alice", role="contributor")
    contrib.post(f"/api/facilities/{published_facility}/fork")

    # Edit topology in personal draft.
    r = contrib.put(
        f"/api/proposals/{published_facility}/topology",
        json=_topology_body(published_facility, 3),
    )
    assert r.status_code == 200
    assert r.json()["nodes"] == 3

    # Submit for review.
    r = contrib.post(
        f"/api/facilities/{published_facility}/submit",
        json={"message": "Add three landmark nodes"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    assert r.json()["source"] == "personal_draft"

    # Admin sees it in the queue.
    admin = client_factory(login="admin-user", role="admin")
    queue = admin.get("/api/proposals").json()
    assert len(queue) == 1
    assert queue[0]["author"] == "alice"
    assert queue[0]["message"] == "Add three landmark nodes"

    # Approve. Forces past validation issues (test data is minimal).
    r = admin.post(
        f"/api/facilities/{published_facility}/proposals/alice/approve",
        json={"force": True},
    )
    assert r.status_code == 200, r.text

    # Published topology now has the contributor's nodes.
    import json

    published = json.loads(
        (workspace / "facilities" / f"{published_facility}.topology.json").read_text()
    )
    assert len(published["nodes"]) == 3

    # Personal draft + proposal sidecar are cleared.
    draft = workspace / "proposals" / "alice" / published_facility
    assert not draft.exists()


def test_reject_keeps_draft_for_iteration(workspace, published_facility, client_factory):
    contrib = client_factory(login="alice", role="contributor")
    contrib.post(f"/api/facilities/{published_facility}/fork")
    contrib.put(
        f"/api/proposals/{published_facility}/topology",
        json=_topology_body(published_facility, 1),
    )
    contrib.post(
        f"/api/facilities/{published_facility}/submit",
        json={"message": "Initial pass"},
    )

    admin = client_factory(login="admin-user", role="admin")
    r = admin.post(
        f"/api/facilities/{published_facility}/proposals/alice/reject",
        json={"review_note": "Needs more landmarks before publish"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "needs_changes"

    # Draft files survive reject — alice can iterate.
    draft = workspace / "proposals" / "alice" / published_facility
    assert (draft / "topology.json").exists()
    assert (draft / "proposal.json").exists()


def test_cross_user_isolation(workspace, published_facility, client_factory):
    """Bob can't read or overwrite Alice's draft."""
    alice = client_factory(login="alice", role="contributor")
    bob = client_factory(login="bob", role="contributor")
    alice.post(f"/api/facilities/{published_facility}/fork")
    alice.put(
        f"/api/proposals/{published_facility}/topology",
        json=_topology_body(published_facility, 5),
    )

    # Bob has no draft of his own.
    r = bob.get(f"/api/proposals/{published_facility}")
    assert r.status_code == 404

    # Bob writing also 404s — the route resolves the draft from his session,
    # not from the URL, so even with a matching slug there's nothing to write.
    r = bob.put(
        f"/api/proposals/{published_facility}/topology",
        json=_topology_body(published_facility, 99),
    )
    assert r.status_code == 404

    # Alice's draft is untouched.
    import json

    alice_topo = json.loads(
        (workspace / "proposals" / "alice" / published_facility / "topology.json").read_text()
    )
    assert len(alice_topo["nodes"]) == 5


def test_facility_editor_submits_from_shared_bootstrap(workspace, client_factory):
    """facility_editor doesn't fork — they edit the shared bootstrap dir
    directly. Submit writes proposal.json into that bootstrap dir."""
    import json

    slug = "shared_test"
    bootstrap = workspace / "bootstrap" / slug
    bootstrap.mkdir(parents=True)
    (bootstrap / "facility.json").write_text(
        json.dumps({"id": slug, "name": "Shared Test", "departments": []})
    )
    (bootstrap / "topology.json").write_text(
        json.dumps({"facility_id": slug, "nodes": [], "edges": []})
    )

    editor = client_factory(login="editor-user", role="facility_editor")
    r = editor.post(
        f"/api/facilities/{slug}/submit",
        json={"message": "Ready for review"},
    )
    assert r.status_code == 200
    assert r.json()["source"] == "shared_bootstrap"

    proposal_path = bootstrap / "proposal.json"
    assert proposal_path.exists()
    body = json.loads(proposal_path.read_text())
    assert body["status"] == "pending"
    assert body["author"] == "editor-user"
