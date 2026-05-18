"""User-uploaded photo service for both edges and nodes.

Mirrors `streetview_edges.py` for the vision-driven edge case but also
supports node-attached photos used purely as editor reviewer reference
(no vision generation). Same EXIF-strip + safe-write pipeline for both.

Storage:
- BOOTSTRAP_DIR/<slug>/photos/edges/<from>__<to>/<uuid>.jpg
- BOOTSTRAP_DIR/<slug>/photos/edges/<from>__<to>/index.json
- BOOTSTRAP_DIR/<slug>/photos/nodes/<node_id>/<uuid>.jpg
- BOOTSTRAP_DIR/<slug>/photos/nodes/<node_id>/index.json

The persisted JPEG is always Pillow-re-encoded (see _io.safe_image_write) so
no attacker-controlled bytes ever land on disk verbatim. EXIF is stripped
except a 5-tag whitelist (lat, lng, alt, heading, timestamp).
"""

from __future__ import annotations

import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import BOOTSTRAP_DIR
from app.services._io import (
    ImageMeta,
    read_json,
    safe_image_write,
    write_json_atomic,
)
from app.services.locate import resolve_paths
from app.services.streetview_edges import (
    load_suggestions,
    scrub_secrets,
    upsert_suggestion,
)


MAX_PHOTOS_PER_EDGE = 10
MAX_BYTES_PER_PHOTO = 10 * 1024 * 1024  # 10 MB
ACCEPTED_MIME = {"image/jpeg", "image/jpg", "image/heic", "image/heif"}
MIN_PHOTOS_TO_GENERATE = 2

_PHOTO_ID_RE = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
_NODE_ID_RE = re.compile(r"^[a-z0-9_]{1,80}$")


def _photos_root(slug: str) -> Path:
    return BOOTSTRAP_DIR / slug / "photos"


def _subject_dir(slug: str, kind: str, sid: str) -> Path:
    return _photos_root(slug) / kind / sid


def _edge_dir(slug: str, edge_id: str) -> Path:
    return _subject_dir(slug, "edges", edge_id)


def _node_dir(slug: str, node_id: str) -> Path:
    return _subject_dir(slug, "nodes", node_id)


def _index_path(subject_dir: Path) -> Path:
    return subject_dir / "index.json"


def edge_id_for(from_id: str, to_id: str) -> str:
    """Stable filesystem key for an edge. Mirrors the (from, to) suggestion key."""
    return f"{from_id}__{to_id}"


def _empty_edge_index(from_id: str, to_id: str) -> dict[str, Any]:
    return {"edge": {"from": from_id, "to": to_id}, "photos": []}


def _empty_node_index(node_id: str) -> dict[str, Any]:
    return {"node": {"id": node_id}, "photos": []}


def _load_subject_index(subject_dir: Path, empty: dict[str, Any]) -> dict[str, Any]:
    path = _index_path(subject_dir)
    if not path.exists():
        return empty
    return read_json(path)


def _save_subject_index(subject_dir: Path, index: dict[str, Any]) -> None:
    write_json_atomic(_index_path(subject_dir), index)


# --- Edge index -----------------------------------------------------------

def load_index(slug: str, from_id: str, to_id: str) -> dict[str, Any]:
    return _load_subject_index(
        _edge_dir(slug, edge_id_for(from_id, to_id)),
        _empty_edge_index(from_id, to_id),
    )


def list_photos(slug: str, from_id: str, to_id: str) -> list[dict[str, Any]]:
    return load_index(slug, from_id, to_id).get("photos", [])


# --- Node index (Phase 2) -------------------------------------------------

def load_node_index(slug: str, node_id: str) -> dict[str, Any]:
    return _load_subject_index(_node_dir(slug, node_id), _empty_node_index(node_id))


def save_node_index(slug: str, node_id: str, index: dict[str, Any]) -> None:
    _save_subject_index(_node_dir(slug, node_id), index)


def list_node_photos(slug: str, node_id: str) -> list[dict[str, Any]]:
    return load_node_index(slug, node_id).get("photos", [])


# --- Photo lookup (proxy) -------------------------------------------------

def photo_path(slug: str, photo_id: str) -> Path | None:
    """Resolve a photo UUID back to its on-disk JPEG. Walks every subject dir
    under <slug>/photos/{edges,nodes}/. Returns None if the file isn't found.
    """
    if not _PHOTO_ID_RE.match(photo_id):
        return None
    root = _photos_root(slug)
    if not root.exists():
        return None
    target = f"{photo_id}.jpg"
    for parent in (root / "edges", root / "nodes"):
        if not parent.exists():
            continue
        for subject_dir in parent.iterdir():
            if not subject_dir.is_dir():
                continue
            candidate = subject_dir / target
            if candidate.exists():
                return candidate
    return None


def _save_uploaded_subject(
    *,
    subject_dir: Path,
    cap_label: str,
    empty_index: dict[str, Any],
    raw: bytes,
    filename: str,
    caption: str | None,
    consent: bool,
    uploaded_by: str,
) -> dict[str, Any]:
    """Generic upload path. Both edges and nodes flow through here."""
    if not consent:
        raise ValueError("Consent flag must be true to upload a photo.")
    if len(raw) == 0:
        raise ValueError("Empty upload.")
    if len(raw) > MAX_BYTES_PER_PHOTO:
        raise ValueError(
            f"Photo exceeds {MAX_BYTES_PER_PHOTO // (1024 * 1024)}MB cap "
            f"(got {len(raw) / (1024 * 1024):.1f}MB)."
        )

    index = _load_subject_index(subject_dir, empty_index)
    if len(index["photos"]) >= MAX_PHOTOS_PER_EDGE:
        raise ValueError(
            f"This {cap_label} already has {MAX_PHOTOS_PER_EDGE} photos (the cap). "
            "Delete one to add another."
        )

    photo_id = str(uuid.uuid4())
    out_path = subject_dir / f"{photo_id}.jpg"
    try:
        meta: ImageMeta = safe_image_write(raw, out_path)
    except Exception as exc:  # Pillow raises a variety of decode errors
        raise ValueError(f"Could not decode upload as an image: {exc}") from exc

    entry = {
        "id": photo_id,
        "filename": f"{photo_id}.jpg",
        "original_filename": filename,
        "caption": (caption or "").strip() or None,
        "lat": meta.lat,
        "lng": meta.lng,
        "alt": meta.alt,
        "heading": meta.heading,
        "timestamp": meta.timestamp,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": uploaded_by,
        "consent": True,
    }
    index["photos"].append(entry)
    _save_subject_index(subject_dir, index)
    return entry


def _reorder_subject(
    subject_dir: Path, empty_index: dict[str, Any], ordered_ids: list[str],
) -> list[dict[str, Any]]:
    index = _load_subject_index(subject_dir, empty_index)
    by_id = {p["id"]: p for p in index["photos"]}
    if set(ordered_ids) != set(by_id):
        raise ValueError("ordered_ids must contain exactly the existing photo IDs.")
    index["photos"] = [by_id[pid] for pid in ordered_ids]
    _save_subject_index(subject_dir, index)
    return index["photos"]


def _update_subject_caption(
    subject_dir: Path, empty_index: dict[str, Any],
    photo_id: str, caption: str | None,
) -> dict[str, Any]:
    index = _load_subject_index(subject_dir, empty_index)
    for p in index["photos"]:
        if p["id"] == photo_id:
            p["caption"] = (caption or "").strip() or None
            _save_subject_index(subject_dir, index)
            return p
    raise LookupError(f"Photo {photo_id} not found.")


def _delete_subject_photo(
    subject_dir: Path, empty_index: dict[str, Any], photo_id: str,
) -> int:
    if not _PHOTO_ID_RE.match(photo_id):
        raise ValueError(f"Invalid photo_id {photo_id!r}.")
    index = _load_subject_index(subject_dir, empty_index)
    before = len(index["photos"])
    index["photos"] = [p for p in index["photos"] if p["id"] != photo_id]
    if len(index["photos"]) == before:
        raise LookupError(f"Photo {photo_id} not found.")
    _save_subject_index(subject_dir, index)
    file = subject_dir / f"{photo_id}.jpg"
    if file.exists():
        file.unlink()
    return len(index["photos"])


# --- Edge public API ------------------------------------------------------

def save_uploaded_photo(
    *, slug: str, from_id: str, to_id: str,
    raw: bytes, filename: str, caption: str | None,
    consent: bool, uploaded_by: str,
) -> dict[str, Any]:
    return _save_uploaded_subject(
        subject_dir=_edge_dir(slug, edge_id_for(from_id, to_id)),
        cap_label="edge",
        empty_index=_empty_edge_index(from_id, to_id),
        raw=raw, filename=filename, caption=caption,
        consent=consent, uploaded_by=uploaded_by,
    )


def reorder_photos(slug: str, from_id: str, to_id: str, ordered_ids: list[str]) -> list[dict[str, Any]]:
    return _reorder_subject(
        _edge_dir(slug, edge_id_for(from_id, to_id)),
        _empty_edge_index(from_id, to_id),
        ordered_ids,
    )


def update_caption(slug: str, from_id: str, to_id: str, photo_id: str, caption: str | None) -> dict[str, Any]:
    return _update_subject_caption(
        _edge_dir(slug, edge_id_for(from_id, to_id)),
        _empty_edge_index(from_id, to_id),
        photo_id, caption,
    )


def delete_photo(slug: str, from_id: str, to_id: str, photo_id: str) -> int:
    return _delete_subject_photo(
        _edge_dir(slug, edge_id_for(from_id, to_id)),
        _empty_edge_index(from_id, to_id),
        photo_id,
    )


# --- Node public API (Phase 2) --------------------------------------------

def _validate_node_id(node_id: str) -> None:
    if not _NODE_ID_RE.match(node_id):
        raise ValueError(f"Invalid node_id {node_id!r}.")


def save_uploaded_node_photo(
    *, slug: str, node_id: str,
    raw: bytes, filename: str, caption: str | None,
    consent: bool, uploaded_by: str,
) -> dict[str, Any]:
    _validate_node_id(node_id)
    return _save_uploaded_subject(
        subject_dir=_node_dir(slug, node_id),
        cap_label="node",
        empty_index=_empty_node_index(node_id),
        raw=raw, filename=filename, caption=caption,
        consent=consent, uploaded_by=uploaded_by,
    )


def reorder_node_photos(slug: str, node_id: str, ordered_ids: list[str]) -> list[dict[str, Any]]:
    _validate_node_id(node_id)
    return _reorder_subject(
        _node_dir(slug, node_id), _empty_node_index(node_id), ordered_ids,
    )


def update_node_caption(slug: str, node_id: str, photo_id: str, caption: str | None) -> dict[str, Any]:
    _validate_node_id(node_id)
    return _update_subject_caption(
        _node_dir(slug, node_id), _empty_node_index(node_id), photo_id, caption,
    )


def delete_node_photo(slug: str, node_id: str, photo_id: str) -> int:
    _validate_node_id(node_id)
    return _delete_subject_photo(
        _node_dir(slug, node_id), _empty_node_index(node_id), photo_id,
    )


# --- Subject-level cascade delete (orphan cleanup) ------------------------

def delete_all_edge_photos(slug: str, from_id: str, to_id: str) -> int:
    """Remove an edge's entire photo directory. Returns the number of photos
    that were on disk (purely informational; a missing dir returns 0)."""
    d = _edge_dir(slug, edge_id_for(from_id, to_id))
    if not d.exists():
        return 0
    count = sum(1 for f in d.iterdir() if f.suffix == ".jpg")
    shutil.rmtree(d)
    return count


def delete_all_node_photos(slug: str, node_id: str) -> int:
    """Remove a node's entire photo directory. Returns the number of photos
    that were on disk."""
    _validate_node_id(node_id)
    d = _node_dir(slug, node_id)
    if not d.exists():
        return 0
    count = sum(1 for f in d.iterdir() if f.suffix == ".jpg")
    shutil.rmtree(d)
    return count


def cleanup_orphans(
    slug: str, *,
    valid_node_ids: set[str],
    valid_edge_keys: set[str],
) -> dict[str, int]:
    """Walk photos/{nodes,edges}/ and remove subject dirs whose subject is no
    longer in the topology. Idempotent; safe to call after every topology
    save. Returns counts of removed dirs.

    Caller computes valid_node_ids and valid_edge_keys from the current
    topology — keeping this service unaware of the topology shape avoids
    importing from app.routes.facilities here.
    """
    nodes_removed = 0
    edges_removed = 0
    nodes_root = _photos_root(slug) / "nodes"
    edges_root = _photos_root(slug) / "edges"
    if nodes_root.exists():
        for d in nodes_root.iterdir():
            if d.is_dir() and d.name not in valid_node_ids:
                shutil.rmtree(d)
                nodes_removed += 1
    if edges_root.exists():
        for d in edges_root.iterdir():
            if d.is_dir() and d.name not in valid_edge_keys:
                shutil.rmtree(d)
                edges_removed += 1
    return {"nodes_removed": nodes_removed, "edges_removed": edges_removed}


# --- Generation -----------------------------------------------------------

_PHOTO_PROMPT = (
    "You are a patient walking from {from_label} on a hospital campus. The "
    "numbered images below are ordered photos taken along the walking path "
    "by an editor, in walk order.\n\n"
    "Write a single wayfinding instruction (1-2 short sentences) describing "
    "what the patient sees, in the voice of a wayfinding instruction "
    "(e.g. \"Walk past the building marked Medical Offices 3, then through "
    "the covered walkway to the entrance with the blue awning\").\n\n"
    "PRIORITIZE READING TEXT in the images. Specific landmarks make "
    "instructions useful; generic ones do not. Look hard for:\n"
    "- Building numbers, building / department names, signage text\n"
    "- Storefronts (cafe, pharmacy, retail), transit signs, awning text\n"
    "- Distinctive colors / materials (glass front, red brick, blue awning)\n\n"
    "Strict rules:\n"
    "- Only claim text you can ACTUALLY READ in the imagery. Quote any "
    "signage you cite, e.g. the sign reading \"MEDICAL OFFICES 3\".\n"
    "- DO NOT use prior knowledge of any hospital, city, or facility. If you "
    "cannot read a building's name in these specific images, do not name it. "
    "Describe visible features instead.\n"
    "- Do not mention compass directions, street names, or distances.\n"
    "- Per-frame editor captions and GPS hints (when present) are CONTEXT "
    "ONLY. Anchor your description in what is visually depicted.\n\n"
    "Return JSON only, no prose, no code fence:\n"
    '{{"landmarks": [string, ...], "instruction": string}}'
)


def _read_jpeg(slug: str, edge_id: str, photo_id: str) -> bytes:
    p = _edge_dir(slug, edge_id) / f"{photo_id}.jpg"
    return p.read_bytes()


def _derive_polyline(photos: list[dict[str, Any]]) -> list[list[float]] | None:
    """Pull lat/lng pairs from photos that have GPS, in order. Need >=2 to
    define a path. Returns [[lat, lng], ...] or None."""
    pts = [
        [p["lat"], p["lng"]]
        for p in photos
        if p.get("lat") is not None and p.get("lng") is not None
    ]
    return pts if len(pts) >= 2 else None


async def generate_from_photos(
    *,
    slug: str,
    from_id: str,
    to_id: str,
) -> dict[str, Any]:
    """Run the vision pipeline over an edge's uploaded photos and upsert a
    suggestion. Returns the suggestion dict.
    """
    # Reuse the SV POC vision module — it's image-source-agnostic. Inline the
    # call here so we can layer per-photo GPS / caption annotations into the
    # prompt without forking the SV vision.py.
    from app.services._io import ensure_streetview_poc_on_path
    ensure_streetview_poc_on_path()
    from streetview_poc.poc.vision import _data_url, _extract_json, VISION_MODEL  # noqa: E402
    from streetview_poc.poc.config import get_client  # noqa: E402

    _facility_path, topology_path, _source = resolve_paths(slug)
    if not topology_path.exists():
        raise FileNotFoundError(f"No topology.json for slug '{slug}'.")
    topology = read_json(topology_path)
    nodes_by_id = {n["id"]: n for n in topology.get("nodes", [])}
    from_node = nodes_by_id.get(from_id)
    to_node = nodes_by_id.get(to_id)
    if not from_node or not to_node:
        raise LookupError(f"node not found: {from_id} or {to_id}")

    photos = list_photos(slug, from_id, to_id)
    if len(photos) < MIN_PHOTOS_TO_GENERATE:
        raise ValueError(
            f"Need at least {MIN_PHOTOS_TO_GENERATE} photos to generate a "
            f"suggestion (have {len(photos)})."
        )

    edge_id = edge_id_for(from_id, to_id)
    from_label = from_node.get("label", from_node["id"])

    # Build multimodal content with per-photo GPS + caption hints inline.
    content: list[dict[str, Any]] = [
        {"type": "text", "text": _PHOTO_PROMPT.format(from_label=from_label)},
    ]
    for i, p in enumerate(photos, start=1):
        annotations = []
        if p.get("lat") is not None and p.get("lng") is not None:
            annotations.append(f"GPS approx {p['lat']:.5f}, {p['lng']:.5f}")
        if p.get("caption"):
            annotations.append(f"editor caption: \"{p['caption']}\"")
        suffix = f" ({'; '.join(annotations)})" if annotations else ""
        content.append({"type": "text", "text": f"Frame {i}{suffix}:"})
        jpeg = _read_jpeg(slug, edge_id, p["id"])
        content.append({"type": "image_url", "image_url": {"url": _data_url(jpeg)}})

    client = get_client()
    try:
        response = await client.chat.completions.create(
            model=VISION_MODEL,
            temperature=0.4,
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
    except Exception as exc:
        raise RuntimeError(scrub_secrets(f"Vision call failed: {exc}")) from exc

    msg = response.choices[0].message
    raw = (msg.content or "").strip()
    if not raw:
        raw = (getattr(msg, "reasoning_content", None) or "").strip()
    if not raw:
        raise RuntimeError(
            "Vision model returned empty content. Try a different "
            "STREETVIEW_VISION_MODEL."
        )
    try:
        parsed = _extract_json(raw)
    except Exception as exc:
        raise RuntimeError(f"Could not parse vision JSON: {exc}\n---\n{raw}") from exc

    polyline = _derive_polyline(photos)
    suggestion = {
        "from": from_id,
        "to": to_id,
        "source": "user_photos",
        "instruction": parsed.get("instruction", ""),
        "landmarks": parsed.get("landmarks", []),
        "photo_metadata": {
            "photo_ids": [p["id"] for p in photos],
            "captions": [p.get("caption") for p in photos],
            "gps_count": sum(
                1 for p in photos
                if p.get("lat") is not None and p.get("lng") is not None
            ),
            "suggested_polyline": polyline,
            "consent_recorded_at": datetime.now(timezone.utc).isoformat(),
            "model": VISION_MODEL,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    upsert_suggestion(slug, suggestion)
    return suggestion


__all__ = [
    "MAX_PHOTOS_PER_EDGE",
    "MAX_BYTES_PER_PHOTO",
    "ACCEPTED_MIME",
    "MIN_PHOTOS_TO_GENERATE",
    "edge_id_for",
    "load_index",
    "list_photos",
    "photo_path",
    "save_uploaded_photo",
    "reorder_photos",
    "update_caption",
    "delete_photo",
    "generate_from_photos",
    "list_node_photos",
    "save_uploaded_node_photo",
    "reorder_node_photos",
    "update_node_caption",
    "delete_node_photo",
    "delete_all_edge_photos",
    "delete_all_node_photos",
    "cleanup_orphans",
]
