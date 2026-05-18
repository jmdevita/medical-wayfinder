"""
Proposal lifecycle endpoints.

Contributors:
  POST   /facilities/{slug}/fork
  GET    /proposals/{slug}            (own draft)
  PUT    /proposals/{slug}/topology
  PUT    /proposals/{slug}/metadata
  PUT    /proposals/{slug}/departments
  DELETE /proposals/{slug}
  POST   /facilities/{slug}/submit    (freeze draft as proposal.json)

Admin:
  GET    /proposals                   (queue across all authors + facilities)
  POST   /facilities/{slug}/proposals/{author}/approve
  POST   /facilities/{slug}/proposals/{author}/reject
  POST   /admin/roles/reload
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from pydantic import BaseModel, Field

from app.auth import (
    CurrentUser,
    ROLES,
    require_admin,
    require_authenticated,
)
from app.paths import BOOTSTRAP_DIR
from app.routes.facilities import (
    DepartmentsPayload,
    MetadataPayload,
    TopologyPayload,
)
from app.routes.publish import (
    PublishResponse,
    load_for_proposal,
    run_publish,
)
from app.services._io import read_json, write_json_atomic
from app.services.proposals import (
    clear_proposal,
    discard_personal_draft,
    fork_published,
    list_pending_proposals,
    personal_draft_dir,
    read_proposal,
    write_proposal,
)
from app.services.publish import compute_warnings, validate_facility

router = APIRouter(tags=["proposals"])

_SLUG_PATTERN = r"^[a-z0-9_]{2,64}$"
SlugParam = Annotated[
    str,
    PathParam(pattern=_SLUG_PATTERN, min_length=2, max_length=64),
]
_AUTHOR_PATTERN = r"^[a-z0-9-]{1,39}$"
AuthorParam = Annotated[
    str,
    PathParam(pattern=_AUTHOR_PATTERN, min_length=1, max_length=39),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _proposal_source_for(user: CurrentUser) -> Literal["personal_draft", "shared_bootstrap"]:
    """facility_editor and admin work in the shared bootstrap; everyone else
    operates on their own personal draft."""
    if user.role in ("facility_editor", "admin"):
        return "shared_bootstrap"
    return "personal_draft"


def _ensure_own_draft(slug: str, user: CurrentUser):
    """All `/proposals/{slug}/*` endpoints write into the caller's *own* draft.
    Looked up from the session — never from the URL — so cross-user writes are
    structurally impossible."""
    draft_dir = personal_draft_dir(user.login, slug)
    if not draft_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No personal draft for '{slug}'. Fork it first.",
        )
    return draft_dir


# ---------------------------------------------------------------------------
# Contributor: fork → edit → submit
# ---------------------------------------------------------------------------

class ForkResponse(BaseModel):
    slug: str
    author: str
    draft_dir: str


@router.post("/facilities/{slug}/fork", response_model=ForkResponse)
def fork(
    slug: SlugParam,
    user: CurrentUser = Depends(require_authenticated),
) -> ForkResponse:
    """Copy the published state of `slug` into the caller's personal draft."""
    try:
        draft_dir = fork_published(slug, user.login)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ForkResponse(slug=slug, author=user.login, draft_dir=str(draft_dir))


@router.get("/proposals/{slug}")
def get_my_draft(
    slug: SlugParam,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    """Read the caller's personal draft. Returns facility + topology + the
    optional proposal sidecar so the frontend can render review status."""
    draft_dir = _ensure_own_draft(slug, user)
    facility = read_json(draft_dir / "facility.json")
    topology = (
        read_json(draft_dir / "topology.json")
        if (draft_dir / "topology.json").exists()
        else None
    )
    proposal = read_proposal(slug=slug, author=user.login, source="personal_draft")
    return {
        "slug": slug,
        "author": user.login,
        "facility": facility,
        "topology": topology,
        "proposal": proposal,
    }


@router.put("/proposals/{slug}/topology")
def save_draft_topology(
    slug: SlugParam,
    payload: TopologyPayload,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    draft_dir = _ensure_own_draft(slug, user)
    data = payload.model_dump()
    data["facility_id"] = slug
    write_json_atomic(draft_dir / "topology.json", data)
    return {
        "slug": slug,
        "saved_to": str(draft_dir / "topology.json"),
        "nodes": len(payload.nodes),
        "edges": len(payload.edges),
    }


@router.put("/proposals/{slug}/metadata")
def save_draft_metadata(
    slug: SlugParam,
    payload: MetadataPayload,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    draft_dir = _ensure_own_draft(slug, user)
    facility_path = draft_dir / "facility.json"
    facility = read_json(facility_path)
    incoming = {k: v for k, v in payload.model_dump().items() if v is not None}
    facility["id"] = slug
    facility["name"] = incoming["name"]
    for key in ("address", "type", "main_phone", "campus_description"):
        if key in incoming:
            facility[key] = incoming[key]
        else:
            facility.pop(key, None)
    facility["buildings"] = incoming.get("buildings", [])
    if incoming.get("parking") is not None:
        facility["parking"] = incoming["parking"]
    if incoming.get("transit") is not None:
        facility["transit"] = incoming["transit"]
    write_json_atomic(facility_path, facility)
    return {"slug": slug, "saved_to": str(facility_path)}


@router.put("/proposals/{slug}/departments")
def save_draft_departments(
    slug: SlugParam,
    payload: DepartmentsPayload,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    draft_dir = _ensure_own_draft(slug, user)
    facility_path = draft_dir / "facility.json"
    facility = read_json(facility_path)
    facility["departments"] = [
        {k: v for k, v in d.model_dump().items() if v is not None}
        for d in payload.departments
    ]
    write_json_atomic(facility_path, facility)
    return {
        "slug": slug,
        "saved_to": str(facility_path),
        "departments": len(payload.departments),
    }


@router.delete("/proposals/{slug}")
def discard_draft(
    slug: SlugParam,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    deleted = discard_personal_draft(slug, user.login)
    if not deleted:
        raise HTTPException(status_code=404, detail="No draft to discard")
    return {"slug": slug, "discarded": True}


class SubmitRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class SubmitResponse(BaseModel):
    slug: str
    author: str
    status: str
    submitted_at: str
    source: str


@router.post("/facilities/{slug}/submit", response_model=SubmitResponse)
def submit_proposal(
    slug: SlugParam,
    body: SubmitRequest,
    user: CurrentUser = Depends(require_authenticated),
) -> SubmitResponse:
    """Freeze the caller's current draft as a `pending` proposal. The source
    (personal draft vs. shared bootstrap) is inferred from the caller's role."""
    source = _proposal_source_for(user)
    if source == "personal_draft":
        _ensure_own_draft(slug, user)
    else:
        # facility_editor / admin path: the bootstrap dir for this slug must
        # already exist (created by the bootstrap pipeline or a prior save).
        # Without this check we'd happily create proposal.json inside a fresh
        # empty dir and surface a phantom proposal in the admin queue.
        if not (BOOTSTRAP_DIR / slug / "facility.json").exists():
            raise HTTPException(
                status_code=404,
                detail=f"No bootstrap workspace for '{slug}' to submit",
            )
    written = write_proposal(
        slug=slug,
        author=user.login,
        message=body.message,
        source=source,
        status="pending",
    )
    return SubmitResponse(
        slug=slug,
        author=user.login,
        status=written["status"],
        submitted_at=written["submitted_at"],
        source=source,
    )


# ---------------------------------------------------------------------------
# Admin: queue, approve, reject, roles reload
# ---------------------------------------------------------------------------

class ProposalSummary(BaseModel):
    slug: str
    author: str
    submitted_at: str
    message: str
    source: str
    status: str
    review_note: str | None = None
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@router.get("/proposals", response_model=list[ProposalSummary])
def list_proposals(_: CurrentUser = Depends(require_admin)) -> list[ProposalSummary]:
    """Pending + needs_changes proposals across the workspace, newest first.
    Each entry runs the same validators as publish dry-run so the admin sees
    issues + warnings inline instead of clicking into each."""
    out: list[ProposalSummary] = []
    for body in list_pending_proposals():
        slug = body["slug"]
        author = body.get("author", "")
        source = body.get("source", "personal_draft")
        try:
            facility, topology = load_for_proposal(slug, author, source)
            issues = validate_facility(facility, topology)
            warnings = compute_warnings(facility, topology)
        except HTTPException as exc:
            issues = [exc.detail if isinstance(exc.detail, str) else "Could not load proposal"]
            warnings = []
        out.append(
            ProposalSummary(
                slug=slug,
                author=author,
                submitted_at=body.get("submitted_at", ""),
                message=body.get("message", ""),
                source=source,
                status=body.get("status", "pending"),
                review_note=body.get("review_note"),
                issues=issues,
                warnings=warnings,
            )
        )
    return out


class ApproveRequest(BaseModel):
    force: bool = False


@router.post("/facilities/{slug}/proposals/{author}/approve", response_model=PublishResponse)
def approve_proposal(
    slug: SlugParam,
    author: AuthorParam,
    body: ApproveRequest | None = None,
    _user: CurrentUser = Depends(require_admin),
) -> PublishResponse:
    """Promote the proposal to published. Skips the editor lock check on
    purpose — a proposal is a frozen snapshot, not live editing."""
    body = body or ApproveRequest()
    proposal = (
        read_proposal(slug=slug, author=author, source="personal_draft")
        or read_proposal(slug=slug, author=author, source="shared_bootstrap")
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="No proposal to approve")
    source = proposal.get("source", "personal_draft")
    facility, topology = load_for_proposal(slug, author, source)
    response = run_publish(slug=slug, facility=facility, topology=topology, force=body.force)
    clear_proposal(slug=slug, author=author, source=source)
    return response


class RejectRequest(BaseModel):
    review_note: str | None = Field(default=None, max_length=2000)


@router.post("/facilities/{slug}/proposals/{author}/reject")
def reject_proposal(
    slug: SlugParam,
    author: AuthorParam,
    body: RejectRequest | None = None,
    _user: CurrentUser = Depends(require_admin),
) -> dict[str, Any]:
    """Mark the proposal `needs_changes` so the author can iterate. Their
    draft files stay untouched."""
    body = body or RejectRequest()
    proposal = (
        read_proposal(slug=slug, author=author, source="personal_draft")
        or read_proposal(slug=slug, author=author, source="shared_bootstrap")
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="No proposal to reject")
    source = proposal.get("source", "personal_draft")
    written = write_proposal(
        slug=slug,
        author=author,
        message=proposal.get("message", ""),
        source=source,
        status="needs_changes",
        review_note=body.review_note,
    )
    return {
        "slug": slug,
        "author": author,
        "status": written["status"],
        "review_note": body.review_note,
    }


# ---------------------------------------------------------------------------
# Admin: roles config hot-reload
# ---------------------------------------------------------------------------

class RolesReloadResponse(BaseModel):
    admin: str
    facility_editors: list[str]


@router.post("/admin/roles/reload", response_model=RolesReloadResponse)
def reload_roles(_: CurrentUser = Depends(require_admin)) -> RolesReloadResponse:
    """Re-read `roles.yaml` without a restart. Returns the new tier set so
    the caller can confirm what's now live."""
    ROLES.reload()
    return RolesReloadResponse(
        admin=ROLES.admin,
        facility_editors=sorted(ROLES.facility_editors),
    )
