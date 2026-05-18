"""Photo edge-walker tests.

Covers safety-critical paths:
- EXIF-strip on persist (no MakerNote, no software, no thumbnail)
- GPS extraction when present, graceful absence when not
- MIME / size / count caps
- Auth gate (only facility_editor)
- accept_suggestion writes geometry from photo polyline

The vision-model call is intentionally NOT exercised here (it would hit a
live LLM endpoint). End-to-end generation is covered by the manual
verification flow.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import piexif
import pytest
from PIL import Image


def _make_jpeg(*, with_gps: bool = False, size: int = 64) -> bytes:
    """Build a minimal JPEG. Optionally embed EXIF GPS + extra non-whitelist tags
    via piexif (Pillow's getexif().tobytes() doesn't round-trip GPS IFDs)."""
    img = Image.new("RGB", (size, size), color=(120, 60, 200))
    buf = io.BytesIO()
    if with_gps:
        zeroth = {
            piexif.ImageIFD.Software: b"TestCam 1.0",
        }
        exif_ifd = {
            piexif.ExifIFD.DateTimeOriginal: b"2026:04:29 14:22:01",
            piexif.ExifIFD.BodySerialNumber: b"SERIAL-DO-NOT-LEAK",
        }
        gps_ifd = {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: ((42, 1), (20, 1), (492, 10)),  # 42.34700
            piexif.GPSIFD.GPSLongitudeRef: b"W",
            piexif.GPSIFD.GPSLongitude: ((71, 1), (6, 1), (0, 1)),     # -71.10000
            piexif.GPSIFD.GPSAltitude: (124, 10),                        # 12.4 m
            piexif.GPSIFD.GPSImgDirection: (187, 1),                     # 187 deg
            piexif.GPSIFD.GPSImgDirectionRef: b"T",
        }
        exif_bytes = piexif.dump({"0th": zeroth, "Exif": exif_ifd, "GPS": gps_ifd})
        img.save(buf, format="JPEG", exif=exif_bytes)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


def _seed_topology(workspace: Path, slug: str = "kaiser_test"):
    """Seed a bootstrap facility with two nodes connected by one edge so the
    photo upload routes have something to attach to."""
    bootstrap = workspace / "bootstrap" / slug
    bootstrap.mkdir(parents=True, exist_ok=True)
    (bootstrap / "facility.json").write_text(json.dumps({
        "id": slug, "name": "Kaiser Test", "address": "1",
        "type": "hospital", "departments": [], "buildings": [],
        "parking": [],
    }))
    (bootstrap / "topology.json").write_text(json.dumps({
        "facility_id": slug, "version": "1.0",
        "nodes": [
            {"id": "a", "label": "Lobby", "lat": 42.347, "lng": -71.100},
            {"id": "b", "label": "Building 3", "lat": 42.348, "lng": -71.101},
        ],
        "edges": [
            {"from": "a", "to": "b", "instruction": "TODO: describe", "geometry": []},
        ],
    }))


# ---------- safe_image_write: EXIF whitelist + GPS extract ----------

def test_safe_image_write_extracts_gps_and_strips_other_exif(workspace, tmp_path):
    """A JPEG with GPS + Software + BodySerial gets persisted with the GPS
    parsed out and the leaky tags dropped. Round-tripping the saved bytes
    through PIL must NOT yield Software/Serial."""
    from app.services._io import safe_image_write

    raw = _make_jpeg(with_gps=True)
    target = tmp_path / "x.jpg"
    meta = safe_image_write(raw, target)

    assert meta.lat is not None and abs(meta.lat - 42.347) < 0.01
    assert meta.lng is not None and abs(meta.lng - (-71.100)) < 0.01
    assert meta.alt is not None and abs(meta.alt - 12.4) < 0.5
    assert meta.heading == 187.0
    assert meta.timestamp == "2026-04-29T14:22:01"

    # Verify the persisted file has no leaky tags.
    persisted = Image.open(target)
    persisted.load()
    surviving = persisted.getexif()
    # Pillow re-encode without exif kwarg -> the saved file has no EXIF block.
    assert 0x0131 not in surviving  # Software
    assert 0xA431 not in surviving  # BodySerialNumber


def test_safe_image_write_no_gps_returns_empty_meta(workspace, tmp_path):
    from app.services._io import safe_image_write

    raw = _make_jpeg(with_gps=False)
    meta = safe_image_write(raw, tmp_path / "y.jpg")
    assert meta.lat is None and meta.lng is None
    assert meta.heading is None


# ---------- service-level upload + index ----------

def _make_heic(*, size: int = 64) -> bytes:
    """Encode a tiny HEIC via pillow-heif. Used to confirm we accept iPhone
    uploads and round-trip them to JPEG on disk."""
    from pillow_heif import from_pillow, register_heif_opener
    register_heif_opener()
    img = Image.new("RGB", (size, size), color=(30, 200, 90))
    heif = from_pillow(img)
    buf = io.BytesIO()
    heif.save(buf, format="HEIF")
    return buf.getvalue()


def test_safe_image_write_accepts_heic_and_persists_as_jpeg(workspace, tmp_path):
    from app.services._io import safe_image_write

    raw = _make_heic()
    target = tmp_path / "iphone.jpg"
    safe_image_write(raw, target)
    # Persisted bytes must be a valid JPEG even though the input was HEIC.
    persisted = Image.open(target)
    persisted.load()
    assert persisted.format == "JPEG"


def test_upload_accepts_heic_mime(workspace, client_factory):
    _seed_topology(workspace)
    editor = client_factory(login="editor-user", role="facility_editor")
    resp = editor.post(
        "/api/photo-edges/kaiser_test/edges/a/b/photos",
        files={"file": ("p.heic", _make_heic(), "image/heic")},
        data={"consent": "true"},
    )
    assert resp.status_code == 200, resp.text
    photo_id = resp.json()["photo"]["id"]
    # Proxied bytes should still be JPEG (re-encoded on disk).
    proxied = editor.get(f"/api/photo-edges/kaiser_test/photos/{photo_id}.jpg")
    assert proxied.status_code == 200
    assert proxied.headers["content-type"] == "image/jpeg"


def test_save_uploaded_photo_persists_index_entry(workspace):
    _seed_topology(workspace)
    from app.services.photo_edges import save_uploaded_photo, list_photos

    raw = _make_jpeg(with_gps=True)
    entry = save_uploaded_photo(
        slug="kaiser_test", from_id="a", to_id="b",
        raw=raw, filename="phone.jpg", caption="lobby",
        consent=True, uploaded_by="editor-user",
    )
    assert entry["lat"] is not None
    assert entry["caption"] == "lobby"
    assert entry["consent"] is True

    photos = list_photos("kaiser_test", "a", "b")
    assert len(photos) == 1
    assert photos[0]["id"] == entry["id"]


def test_save_rejects_no_consent(workspace):
    _seed_topology(workspace)
    from app.services.photo_edges import save_uploaded_photo

    with pytest.raises(ValueError, match="[Cc]onsent"):
        save_uploaded_photo(
            slug="kaiser_test", from_id="a", to_id="b",
            raw=_make_jpeg(), filename="x.jpg", caption=None,
            consent=False, uploaded_by="editor-user",
        )


def test_save_rejects_oversized(workspace):
    _seed_topology(workspace)
    from app.services.photo_edges import save_uploaded_photo, MAX_BYTES_PER_PHOTO

    # Build a fake "raw" that exceeds the cap. Pillow won't decode it — but
    # the size check fires first.
    too_big = b"\xff\xd8" + b"\x00" * (MAX_BYTES_PER_PHOTO + 1)
    with pytest.raises(ValueError, match="cap"):
        save_uploaded_photo(
            slug="kaiser_test", from_id="a", to_id="b",
            raw=too_big, filename="big.jpg", caption=None,
            consent=True, uploaded_by="editor-user",
        )


def test_save_enforces_max_count(workspace):
    _seed_topology(workspace)
    from app.services.photo_edges import save_uploaded_photo, MAX_PHOTOS_PER_EDGE

    raw = _make_jpeg()
    for _ in range(MAX_PHOTOS_PER_EDGE):
        save_uploaded_photo(
            slug="kaiser_test", from_id="a", to_id="b",
            raw=raw, filename="x.jpg", caption=None,
            consent=True, uploaded_by="editor-user",
        )
    with pytest.raises(ValueError, match="cap"):
        save_uploaded_photo(
            slug="kaiser_test", from_id="a", to_id="b",
            raw=raw, filename="x.jpg", caption=None,
            consent=True, uploaded_by="editor-user",
        )


def test_delete_removes_file_and_entry(workspace):
    _seed_topology(workspace)
    from app.services.photo_edges import (
        delete_photo, edge_id_for, list_photos, save_uploaded_photo,
    )
    from app.paths import BOOTSTRAP_DIR

    entry = save_uploaded_photo(
        slug="kaiser_test", from_id="a", to_id="b",
        raw=_make_jpeg(), filename="x.jpg", caption=None,
        consent=True, uploaded_by="editor-user",
    )
    file = BOOTSTRAP_DIR / "kaiser_test" / "photos" / "edges" / edge_id_for("a", "b") / f"{entry['id']}.jpg"
    assert file.exists()
    remaining = delete_photo("kaiser_test", "a", "b", entry["id"])
    assert remaining == 0
    assert not file.exists()
    assert list_photos("kaiser_test", "a", "b") == []


# ---------- accept_suggestion writes polyline geometry ----------

def test_accept_writes_photo_polyline_to_topology(workspace):
    _seed_topology(workspace)
    from app.services.streetview_edges import accept_suggestion, save_suggestions

    polyline = [[42.347, -71.100], [42.3475, -71.1005], [42.348, -71.101]]
    save_suggestions("kaiser_test", {
        "slug": "kaiser_test",
        "generated_at": "2026-04-29T00:00:00+00:00",
        "suggestions": [{
            "from": "a", "to": "b",
            "source": "user_photos",
            "instruction": "Walk past the lobby and through the glass doors.",
            "landmarks": ["lobby"],
            "photo_metadata": {
                "photo_ids": ["uuid-1", "uuid-2", "uuid-3"],
                "captions": [None, None, None],
                "gps_count": 3,
                "suggested_polyline": polyline,
                "consent_recorded_at": "2026-04-29T00:00:00+00:00",
                "model": "test",
            },
            "generated_at": "2026-04-29T00:00:00+00:00",
        }],
    })
    result = accept_suggestion("kaiser_test", "a", "b")
    assert result["geometry_replaced"] is True
    assert result["source"] == "user_photos"

    topology = json.loads(
        (workspace / "bootstrap" / "kaiser_test" / "topology.json").read_text()
    )
    edge = topology["edges"][0]
    assert edge["instruction"].startswith("Walk past the lobby")
    assert edge["geometry"] == polyline


def test_accept_user_photos_with_replace_geometry_false_preserves_geometry(workspace):
    _seed_topology(workspace)
    from app.services.streetview_edges import accept_suggestion, save_suggestions

    polyline = [[42.347, -71.100], [42.348, -71.101]]
    save_suggestions("kaiser_test", {
        "slug": "kaiser_test",
        "generated_at": "2026-04-29T00:00:00+00:00",
        "suggestions": [{
            "from": "a", "to": "b",
            "source": "user_photos",
            "instruction": "Walk past the lobby.",
            "landmarks": [],
            "photo_metadata": {
                "photo_ids": ["x", "y"],
                "captions": [None, None],
                "gps_count": 2,
                "suggested_polyline": polyline,
                "consent_recorded_at": "2026-04-29T00:00:00+00:00",
                "model": "test",
            },
            "generated_at": "2026-04-29T00:00:00+00:00",
        }],
    })
    result = accept_suggestion("kaiser_test", "a", "b", replace_geometry=False)
    assert result["geometry_replaced"] is False
    topology = json.loads(
        (workspace / "bootstrap" / "kaiser_test" / "topology.json").read_text()
    )
    # Seed topology had geometry: [], must remain [].
    assert topology["edges"][0]["geometry"] == []
    assert topology["edges"][0]["instruction"] == "Walk past the lobby."


def test_accept_streetview_does_not_touch_geometry(workspace):
    _seed_topology(workspace)
    from app.services.streetview_edges import accept_suggestion, save_suggestions

    save_suggestions("kaiser_test", {
        "slug": "kaiser_test",
        "generated_at": "2026-04-29T00:00:00+00:00",
        "suggestions": [{
            "from": "a", "to": "b",
            "source": "streetview",
            "instruction": "Walk down the path.",
            "landmarks": [],
            "routing": {"method": "straight_line", "routed_m": None, "polyline_points": None},
            "coverage": {"verdict": "warn", "metrics": {}, "reasons": []},
            "evidence": {"pano_ids": [], "pano_dates": [], "model": "x"},
            "generated_at": "2026-04-29T00:00:00+00:00",
        }],
    })
    result = accept_suggestion("kaiser_test", "a", "b")
    assert result["geometry_replaced"] is False

    topology = json.loads(
        (workspace / "bootstrap" / "kaiser_test" / "topology.json").read_text()
    )
    # Geometry was [] in the seed — accept must not have overwritten it.
    assert topology["edges"][0]["geometry"] == []


# ---------- HTTP-level: auth gate + MIME/size validations ----------

def test_upload_requires_facility_editor(workspace, client_factory):
    _seed_topology(workspace)
    contrib = client_factory(login="alice", role="contributor")
    resp = contrib.post(
        "/api/photo-edges/kaiser_test/edges/a/b/photos",
        files={"file": ("p.jpg", _make_jpeg(), "image/jpeg")},
        data={"consent": "true"},
    )
    assert resp.status_code == 401


def test_upload_rejects_non_jpeg(workspace, client_factory):
    _seed_topology(workspace)
    editor = client_factory(login="editor-user", role="facility_editor")
    resp = editor.post(
        "/api/photo-edges/kaiser_test/edges/a/b/photos",
        files={"file": ("p.png", b"\x89PNG\r\n", "image/png")},
        data={"consent": "true"},
    )
    assert resp.status_code == 415


def test_upload_rejects_missing_consent(workspace, client_factory):
    _seed_topology(workspace)
    editor = client_factory(login="editor-user", role="facility_editor")
    resp = editor.post(
        "/api/photo-edges/kaiser_test/edges/a/b/photos",
        files={"file": ("p.jpg", _make_jpeg(), "image/jpeg")},
        data={"consent": "false"},
    )
    assert resp.status_code == 422


def test_upload_then_list_then_delete(workspace, client_factory):
    _seed_topology(workspace)
    editor = client_factory(login="editor-user", role="facility_editor")

    up = editor.post(
        "/api/photo-edges/kaiser_test/edges/a/b/photos",
        files={"file": ("p.jpg", _make_jpeg(with_gps=True), "image/jpeg")},
        data={"consent": "true", "caption": "lobby"},
    )
    assert up.status_code == 200, up.text
    photo_id = up.json()["photo"]["id"]

    listed = editor.get("/api/photo-edges/kaiser_test/edges/a/b/photos")
    assert listed.status_code == 200
    assert len(listed.json()["photos"]) == 1

    proxied = editor.get(f"/api/photo-edges/kaiser_test/photos/{photo_id}.jpg")
    assert proxied.status_code == 200
    assert proxied.headers["content-type"] == "image/jpeg"

    deleted = editor.delete(
        f"/api/photo-edges/kaiser_test/edges/a/b/photos/{photo_id}"
    )
    assert deleted.status_code == 200
    assert deleted.json()["remaining"] == 0


def test_proxy_requires_facility_editor(workspace, client_factory):
    _seed_topology(workspace)
    editor = client_factory(login="editor-user", role="facility_editor")
    up = editor.post(
        "/api/photo-edges/kaiser_test/edges/a/b/photos",
        files={"file": ("p.jpg", _make_jpeg(), "image/jpeg")},
        data={"consent": "true"},
    )
    photo_id = up.json()["photo"]["id"]
    contrib = client_factory(login="alice", role="contributor")
    resp = contrib.get(f"/api/photo-edges/kaiser_test/photos/{photo_id}.jpg")
    assert resp.status_code == 401


def test_upload_node_photo_persists(workspace, client_factory):
    _seed_topology(workspace)
    editor = client_factory(login="editor-user", role="facility_editor")
    resp = editor.post(
        "/api/photo-edges/kaiser_test/nodes/a/photos",
        files={"file": ("p.jpg", _make_jpeg(with_gps=True), "image/jpeg")},
        data={"consent": "true", "caption": "lobby with elevator"},
    )
    assert resp.status_code == 200, resp.text
    photo_id = resp.json()["photo"]["id"]
    listed = editor.get("/api/photo-edges/kaiser_test/nodes/a/photos")
    assert listed.status_code == 200
    assert len(listed.json()["photos"]) == 1
    assert listed.json()["photos"][0]["caption"] == "lobby with elevator"
    proxied = editor.get(f"/api/photo-edges/kaiser_test/photos/{photo_id}.jpg")
    assert proxied.status_code == 200
    assert proxied.headers["content-type"] == "image/jpeg"


def test_node_photo_no_generate_route(workspace, client_factory):
    """There must be no /nodes/<id>/generate endpoint — vision generation
    only makes sense for ordered walking sequences (edges)."""
    _seed_topology(workspace)
    editor = client_factory(login="editor-user", role="facility_editor")
    resp = editor.post("/api/photo-edges/kaiser_test/nodes/a/generate")
    assert resp.status_code == 404


def test_node_photo_delete(workspace, client_factory):
    _seed_topology(workspace)
    editor = client_factory(login="editor-user", role="facility_editor")
    up = editor.post(
        "/api/photo-edges/kaiser_test/nodes/a/photos",
        files={"file": ("p.jpg", _make_jpeg(), "image/jpeg")},
        data={"consent": "true"},
    )
    photo_id = up.json()["photo"]["id"]
    deleted = editor.delete(
        f"/api/photo-edges/kaiser_test/nodes/a/photos/{photo_id}"
    )
    assert deleted.status_code == 200
    assert deleted.json()["remaining"] == 0


def test_node_photo_requires_facility_editor(workspace, client_factory):
    _seed_topology(workspace)
    contrib = client_factory(login="alice", role="contributor")
    resp = contrib.post(
        "/api/photo-edges/kaiser_test/nodes/a/photos",
        files={"file": ("p.jpg", _make_jpeg(), "image/jpeg")},
        data={"consent": "true"},
    )
    assert resp.status_code == 401


def test_cascade_delete_node_photos(workspace, client_factory):
    _seed_topology(workspace)
    editor = client_factory(login="editor-user", role="facility_editor")
    for _ in range(3):
        editor.post(
            "/api/photo-edges/kaiser_test/nodes/a/photos",
            files={"file": ("p.jpg", _make_jpeg(), "image/jpeg")},
            data={"consent": "true"},
        )
    resp = editor.delete("/api/photo-edges/kaiser_test/nodes/a/photos")
    assert resp.status_code == 200
    assert resp.json()["removed"] == 3
    listed = editor.get("/api/photo-edges/kaiser_test/nodes/a/photos")
    assert listed.json()["photos"] == []


def test_cascade_delete_edge_photos(workspace, client_factory):
    _seed_topology(workspace)
    editor = client_factory(login="editor-user", role="facility_editor")
    editor.post(
        "/api/photo-edges/kaiser_test/edges/a/b/photos",
        files={"file": ("p.jpg", _make_jpeg(), "image/jpeg")},
        data={"consent": "true"},
    )
    resp = editor.delete("/api/photo-edges/kaiser_test/edges/a/b/photos")
    assert resp.status_code == 200
    assert resp.json()["removed"] == 1


def test_cleanup_orphans_removes_stale_subject_dirs(workspace):
    _seed_topology(workspace)
    from app.services.photo_edges import (
        cleanup_orphans, save_uploaded_node_photo, save_uploaded_photo,
    )

    save_uploaded_photo(
        slug="kaiser_test", from_id="a", to_id="b",
        raw=_make_jpeg(), filename="x.jpg", caption=None,
        consent=True, uploaded_by="editor-user",
    )
    save_uploaded_node_photo(
        slug="kaiser_test", node_id="a",
        raw=_make_jpeg(), filename="y.jpg", caption=None,
        consent=True, uploaded_by="editor-user",
    )
    # Pretend topology no longer has node "a" or the edge a->b.
    result = cleanup_orphans(
        "kaiser_test",
        valid_node_ids={"b"},     # "a" is now a stale node dir
        valid_edge_keys=set(),    # no edges valid
    )
    assert result == {"nodes_removed": 1, "edges_removed": 1}
    # Idempotent.
    again = cleanup_orphans(
        "kaiser_test", valid_node_ids={"b"}, valid_edge_keys=set(),
    )
    assert again == {"nodes_removed": 0, "edges_removed": 0}


def test_generate_requires_two_photos(workspace, client_factory):
    _seed_topology(workspace)
    editor = client_factory(login="editor-user", role="facility_editor")
    editor.post(
        "/api/photo-edges/kaiser_test/edges/a/b/photos",
        files={"file": ("p.jpg", _make_jpeg(), "image/jpeg")},
        data={"consent": "true"},
    )
    resp = editor.post(
        "/api/photo-edges/kaiser_test/edges/a/b/generate"
    )
    assert resp.status_code == 422
    assert "at least" in resp.json()["detail"].lower()
