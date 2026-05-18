"""
Proposal storage helpers.

Two flavors of proposal coexist:

  source=personal_draft   Lives at  PROPOSALS_DIR/<author>/<slug>/{facility,topology,proposal}.json
                          Created by a contributor who forked the published
                          state. Edits never touch the shared bootstrap dir.

  source=shared_bootstrap Lives at  BOOTSTRAP_DIR/<slug>/{facility,topology,osm}.json
                          plus an optional proposal.json sidecar that flips
                          the in-progress draft to a "ready for review" state.

Admin's approve/reject endpoints handle both shapes uniformly; everything in
this module reads/writes the underlying paths and never adjudicates publish
itself — that's still publish.py's job.
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path
from typing import Any, Literal

from app.paths import BOOTSTRAP_DIR, FACILITIES_DIR, PROPOSALS_DIR
from app.services._io import read_json, write_json_atomic

ProposalSource = Literal["personal_draft", "shared_bootstrap"]
ProposalStatus = Literal["draft", "pending", "needs_changes"]

# Slug authors come from a GitHub login string (lowercased) — restrict to a
# safe character set before we use them in filesystem paths.
_AUTHOR_PATTERN = re.compile(r"^[a-z0-9-]{1,39}$")


def _author_dir(author: str) -> Path:
    if not _AUTHOR_PATTERN.match(author):
        raise ValueError(f"invalid author slug: {author!r}")
    return PROPOSALS_DIR / author


def personal_draft_dir(author: str, slug: str) -> Path:
    return _author_dir(author) / slug


def proposal_path(author: str, slug: str, source: ProposalSource) -> Path:
    if source == "personal_draft":
        return personal_draft_dir(author, slug) / "proposal.json"
    return BOOTSTRAP_DIR / slug / "proposal.json"


def fork_published(slug: str, author: str) -> Path:
    """Copy the currently-published facility + topology into the contributor's
    personal draft dir. Idempotent for the *missing-target* case: if the dir
    already exists we don't overwrite, so the contributor doesn't accidentally
    lose in-progress edits when they re-click "Fork to edit"."""
    src_facility = FACILITIES_DIR / f"{slug}.json"
    src_topology = FACILITIES_DIR / f"{slug}.topology.json"
    if not src_facility.exists():
        raise FileNotFoundError(f"facility '{slug}' is not published")

    target = personal_draft_dir(author, slug)
    if target.exists():
        return target

    target.mkdir(parents=True, exist_ok=True)
    facility = read_json(src_facility)
    write_json_atomic(target / "facility.json", facility)
    if src_topology.exists():
        topology = read_json(src_topology)
        write_json_atomic(target / "topology.json", topology)
    return target


def discard_personal_draft(slug: str, author: str) -> bool:
    """Drop the contributor's personal draft. Returns True if anything was
    deleted, False if the draft didn't exist."""
    target = personal_draft_dir(author, slug)
    if not target.exists():
        return False
    shutil.rmtree(target)
    return True


def write_proposal(
    *,
    slug: str,
    author: str,
    message: str,
    source: ProposalSource,
    status: ProposalStatus = "pending",
    review_note: str | None = None,
) -> dict[str, Any]:
    """Write the proposal.json sidecar. Used both at submit-time (status=pending)
    and when admin rejects (status=needs_changes, with a review_note)."""
    path = proposal_path(author, slug, source)
    body: dict[str, Any] = {
        "author": author,
        "submitted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "message": message,
        "source": source,
        "status": status,
    }
    if review_note is not None:
        body["review_note"] = review_note
    write_json_atomic(path, body)
    return body


def read_proposal(
    *, slug: str, author: str, source: ProposalSource
) -> dict[str, Any] | None:
    path = proposal_path(author, slug, source)
    if not path.exists():
        return None
    return read_json(path)


def clear_proposal(*, slug: str, author: str, source: ProposalSource) -> None:
    """Remove the proposal.json sidecar after approve. Personal-draft files
    are also cleaned up since the published version is now authoritative."""
    path = proposal_path(author, slug, source)
    if path.exists():
        path.unlink()
    if source == "personal_draft":
        # The personal draft dir as a whole no longer needs to live — the
        # contributor can re-fork from the new published state if they want
        # to keep iterating.
        target = personal_draft_dir(author, slug)
        if target.exists():
            shutil.rmtree(target)


def list_pending_proposals() -> list[dict[str, Any]]:
    """All proposal.json sidecars with status in {pending, needs_changes}.
    Each entry includes enough info for the admin queue to render without
    further round-trips. Returned newest-first by submitted_at."""
    found: list[dict[str, Any]] = []

    if PROPOSALS_DIR.exists():
        for author_dir in PROPOSALS_DIR.iterdir():
            if not author_dir.is_dir():
                continue
            for slug_dir in author_dir.iterdir():
                if not slug_dir.is_dir():
                    continue
                p = slug_dir / "proposal.json"
                if not p.exists():
                    continue
                try:
                    body = read_json(p)
                except Exception:
                    continue
                if body.get("status") in ("pending", "needs_changes"):
                    body.setdefault("slug", slug_dir.name)
                    body.setdefault("source", "personal_draft")
                    found.append(body)

    if BOOTSTRAP_DIR.exists():
        for slug_dir in BOOTSTRAP_DIR.iterdir():
            if not slug_dir.is_dir():
                continue
            p = slug_dir / "proposal.json"
            if not p.exists():
                continue
            try:
                body = read_json(p)
            except Exception:
                continue
            if body.get("status") in ("pending", "needs_changes"):
                body.setdefault("slug", slug_dir.name)
                body.setdefault("source", "shared_bootstrap")
                found.append(body)

    found.sort(key=lambda b: b.get("submitted_at", ""), reverse=True)
    return found
