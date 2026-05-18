import { QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FacilityMeta, Topology } from "./types";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const API_BASE = "/api";

export class ApiError extends Error {
  status: number;
  body: string;
  constructor(status: number, message: string, body = "") {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "same-origin", // send the session cookie
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (res.status === 401) {
    // Not signed in. Stash the current location and bounce through the
    // backend's GitHub OAuth dance. The /auth/me query suppresses this so
    // the dashboard can still render its "Sign in" UI for unauthed users.
    if (path !== "/auth/me") {
      const ret = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/api/auth/login?return_to=${ret}`;
    }
    throw new ApiError(401, "Not signed in");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(
      res.status,
      `${res.status} ${res.statusText} \u2014 ${path}${text ? `: ${text}` : ""}`,
      text,
    );
  }
  return (await res.json()) as T;
}

// ----- raw API -----

export interface FacilityDetail {
  slug: string;
  source: "published" | "bootstrap";
  facility: Record<string, unknown> & { name: string; departments?: unknown[] };
  topology: Topology | null;
}

export interface JobKickoffResponse {
  job_id: string;
  slug: string;
  stream_url: string;
}

export interface BootstrapRequest {
  query: string;
  slug?: string;
  include_landmarks?: boolean;
}

export interface ExtractDepartmentsRequest {
  slug: string;
  urls: string[];
  model?: string;
  base_url?: string;
}

export interface DraftEdgesRequest {
  slug: string;
  max_dist?: number;
}

export interface StreetviewEdgesRequest {
  slug: string;
  use_routing?: boolean;
  image_call_cap?: number;
}

export type CoverageVerdict = "pass" | "warn" | "fail";

export interface SuggestionEvidence {
  pano_ids: string[];
  pano_dates: (string | null)[];
  model: string | null;
}

export type SuggestionSource = "streetview" | "user_photos";

export interface PhotoSuggestionMetadata {
  photo_ids: string[];
  captions: (string | null)[];
  gps_count: number;
  suggested_polyline: [number, number][] | null;
  consent_recorded_at: string;
  model: string | null;
}

export interface Suggestion {
  from: string;
  to: string;
  /** Defaults to "streetview" when absent (older sidecars). */
  source?: SuggestionSource;
  instruction: string | null;
  landmarks: string[];
  /** Street View suggestions only. */
  routing?: {
    method: "osm_footway" | "straight_line";
    routed_m: number | null;
    polyline_points: number | null;
  };
  /** Street View suggestions only. */
  coverage?: {
    verdict: CoverageVerdict;
    metrics: Record<string, number | string | null>;
    reasons: string[];
  };
  /** Street View suggestions only. */
  evidence?: SuggestionEvidence;
  /** User-photo suggestions only. */
  photo_metadata?: PhotoSuggestionMetadata;
  skipped_reason?: string;
  generated_at: string;
}

export interface EdgePhoto {
  id: string;
  filename: string;
  original_filename: string;
  caption: string | null;
  lat: number | null;
  lng: number | null;
  alt: number | null;
  heading: number | null;
  timestamp: string | null;
  uploaded_at: string;
  uploaded_by: string;
  consent: boolean;
}

export interface EdgePhotosResponse {
  slug: string;
  from: string;
  to: string;
  photos: EdgePhoto[];
}

export interface SuggestionsSidecar {
  slug: string;
  generated_at: string;
  suggestions: Suggestion[];
}

export interface ExpandAliasesRequest {
  slug: string;
  model?: string;
  base_url?: string;
}

export interface PublishDryRun {
  slug: string;
  ok: boolean;
  issues: string[];
  warnings: string[];
}

export interface PublishResponse {
  slug: string;
  facility_path: string;
  topology_path: string;
  issues: string[];
  warnings: string[];
}

export interface TestConnectionRequest {
  base_url?: string;
  model?: string;
  timeout_s?: number;
}

export interface TestConnectionResponse {
  ok: boolean;
  base_url: string;
  model: string;
  latency_ms: number | null;
  sample: string | null;
  error: string | null;
}

export interface CurrentSettings {
  base_url: string;
  model: string;
  cors_origins: string[];
  facilities_dir: string;
  bootstrap_dir: string;
  /** True when the backend has ATLAS_DEMO_MODE=true; signals the frontend
   *  to render the demo banner and treat write-action 503s as expected. */
  demo_mode: boolean;
}

export type Role = "viewer" | "contributor" | "facility_editor" | "admin";

export interface WhoAmI {
  login: string | null;
  auth_enforced: boolean;
  authenticated: boolean;
  role: Role;
}

export interface LockStatus {
  slug: string;
  locked: boolean;
  held_by?: string;
  acquired_at?: number;
  last_heartbeat?: number;
  ttl_seconds: number;
}

export interface ProposalDraft {
  slug: string;
  author: string;
  facility: Record<string, unknown> & { name?: string; departments?: unknown[] };
  topology: Topology | null;
  proposal: ProposalSidecar | null;
}

export interface ProposalSidecar {
  author: string;
  submitted_at: string;
  message: string;
  source: "personal_draft" | "shared_bootstrap";
  status: "draft" | "pending" | "needs_changes";
  review_note?: string;
}

export interface ProposalSummary {
  slug: string;
  author: string;
  submitted_at: string;
  message: string;
  source: "personal_draft" | "shared_bootstrap";
  status: "pending" | "needs_changes";
  review_note?: string | null;
  issues: string[];
  warnings: string[];
}

export interface SubmitResponse {
  slug: string;
  author: string;
  status: string;
  submitted_at: string;
  source: string;
}

export const api = {
  listFacilities: () => request<{ facilities: FacilityMeta[] }>("/facilities"),
  currentSettings: () => request<CurrentSettings>("/settings/current"),
  testConnection: (body: TestConnectionRequest) =>
    request<TestConnectionResponse>("/settings/test-connection", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getFacility:    (slug: string) => request<FacilityDetail>(`/facilities/${slug}`),
  saveTopology:   (slug: string, topology: Topology) =>
    request<{ slug: string; saved_to: string; nodes: number; edges: number }>(
      `/facilities/${slug}/topology`,
      { method: "PUT", body: JSON.stringify(topology) },
    ),
  bootstrap: (body: BootstrapRequest) =>
    request<JobKickoffResponse>("/bootstrap", { method: "POST", body: JSON.stringify(body) }),
  extractDepartments: (body: ExtractDepartmentsRequest) =>
    request<JobKickoffResponse>("/extract-departments", { method: "POST", body: JSON.stringify(body) }),
  draftEdges: (body: DraftEdgesRequest) =>
    request<JobKickoffResponse>("/draft-edges", { method: "POST", body: JSON.stringify(body) }),
  streetviewEdgesBulk: (body: StreetviewEdgesRequest) =>
    request<JobKickoffResponse>("/streetview-edges", { method: "POST", body: JSON.stringify(body) }),
  getSuggestions: (slug: string) =>
    request<SuggestionsSidecar>(`/streetview-edges/${slug}/suggestions`),
  regenerateSuggestion: (slug: string, fromId: string, toId: string, useRouting = true) =>
    request<Suggestion>(
      `/streetview-edges/${slug}/edges/${fromId}/${toId}/regenerate`,
      { method: "POST", body: JSON.stringify({ use_routing: useRouting }) },
    ),
  acceptSuggestion: (
    slug: string, fromId: string, toId: string,
    replaceGeometry = true,
  ) =>
    request<{ slug: string; topology_path: string; instruction: string; geometry_replaced: boolean; source: string }>(
      `/streetview-edges/${slug}/accept`,
      {
        method: "POST",
        body: JSON.stringify({
          from_id: fromId, to_id: toId, replace_geometry: replaceGeometry,
        }),
      },
    ),
  discardSuggestion: (slug: string, fromId: string, toId: string) =>
    request<{ slug: string; remaining: number }>(
      `/streetview-edges/${slug}/suggestions/${fromId}/${toId}`,
      { method: "DELETE" },
    ),
  panoUrl: (slug: string, panoId: string, heading = 0): string =>
    `${API_BASE}/streetview-edges/${slug}/panos/${panoId}.jpg?heading=${heading.toFixed(2)}`,
  // --- Photo edge-walker (docs/29) ---
  photoUrl: (slug: string, photoId: string): string =>
    `${API_BASE}/photo-edges/${slug}/photos/${photoId}.jpg`,
  uploadEdgePhoto: async (
    slug: string, fromId: string, toId: string,
    file: File, caption: string | null, consent: boolean,
  ) => {
    const form = new FormData();
    form.append("file", file);
    if (caption) form.append("caption", caption);
    form.append("consent", consent ? "true" : "false");
    const res = await fetch(
      `${API_BASE}/photo-edges/${slug}/edges/${fromId}/${toId}/photos`,
      { method: "POST", credentials: "include", body: form },
    );
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try { detail = (await res.json()).detail ?? detail; } catch { /* noop */ }
      throw new Error(detail);
    }
    return res.json() as Promise<{ slug: string; from: string; to: string; photo: EdgePhoto }>;
  },
  listEdgePhotos: (slug: string, fromId: string, toId: string) =>
    request<EdgePhotosResponse>(
      `/photo-edges/${slug}/edges/${fromId}/${toId}/photos`,
    ),
  reorderEdgePhotos: (slug: string, fromId: string, toId: string, photoIds: string[]) =>
    request<EdgePhotosResponse>(
      `/photo-edges/${slug}/edges/${fromId}/${toId}/photos/order`,
      { method: "PATCH", body: JSON.stringify({ photo_ids: photoIds }) },
    ),
  updateEdgePhotoCaption: (
    slug: string, fromId: string, toId: string, photoId: string, caption: string | null,
  ) =>
    request<{ photo: EdgePhoto }>(
      `/photo-edges/${slug}/edges/${fromId}/${toId}/photos/${photoId}`,
      { method: "PATCH", body: JSON.stringify({ caption }) },
    ),
  deleteEdgePhoto: (slug: string, fromId: string, toId: string, photoId: string) =>
    request<{ slug: string; from: string; to: string; remaining: number }>(
      `/photo-edges/${slug}/edges/${fromId}/${toId}/photos/${photoId}`,
      { method: "DELETE" },
    ),
  // Cascade delete — wipes the entire subject's photo dir. Used when the
  // node/edge itself is being removed so on-disk orphans don't accumulate.
  deleteAllEdgePhotos: (slug: string, fromId: string, toId: string) =>
    request<{ slug: string; from: string; to: string; removed: number }>(
      `/photo-edges/${slug}/edges/${fromId}/${toId}/photos`,
      { method: "DELETE" },
    ),
  deleteAllNodePhotos: (slug: string, nodeId: string) =>
    request<{ slug: string; node_id: string; removed: number }>(
      `/photo-edges/${slug}/nodes/${nodeId}/photos`,
      { method: "DELETE" },
    ),
  generateFromPhotos: (slug: string, fromId: string, toId: string) =>
    request<Suggestion>(
      `/photo-edges/${slug}/edges/${fromId}/${toId}/generate`,
      { method: "POST", body: JSON.stringify({}) },
    ),
  // Node-attached photos (editor reviewer reference; no vision generation).
  uploadNodePhoto: async (
    slug: string, nodeId: string,
    file: File, caption: string | null, consent: boolean,
  ) => {
    const form = new FormData();
    form.append("file", file);
    if (caption) form.append("caption", caption);
    form.append("consent", consent ? "true" : "false");
    const res = await fetch(
      `${API_BASE}/photo-edges/${slug}/nodes/${nodeId}/photos`,
      { method: "POST", credentials: "include", body: form },
    );
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try { detail = (await res.json()).detail ?? detail; } catch { /* noop */ }
      throw new Error(detail);
    }
    return res.json() as Promise<{ slug: string; node_id: string; photo: EdgePhoto }>;
  },
  listNodePhotos: (slug: string, nodeId: string) =>
    request<{ slug: string; node_id: string; photos: EdgePhoto[] }>(
      `/photo-edges/${slug}/nodes/${nodeId}/photos`,
    ),
  reorderNodePhotos: (slug: string, nodeId: string, photoIds: string[]) =>
    request<{ slug: string; node_id: string; photos: EdgePhoto[] }>(
      `/photo-edges/${slug}/nodes/${nodeId}/photos/order`,
      { method: "PATCH", body: JSON.stringify({ photo_ids: photoIds }) },
    ),
  updateNodePhotoCaption: (slug: string, nodeId: string, photoId: string, caption: string | null) =>
    request<{ photo: EdgePhoto }>(
      `/photo-edges/${slug}/nodes/${nodeId}/photos/${photoId}`,
      { method: "PATCH", body: JSON.stringify({ caption }) },
    ),
  deleteNodePhoto: (slug: string, nodeId: string, photoId: string) =>
    request<{ slug: string; node_id: string; remaining: number }>(
      `/photo-edges/${slug}/nodes/${nodeId}/photos/${photoId}`,
      { method: "DELETE" },
    ),
  expandAliases: (body: ExpandAliasesRequest) =>
    request<JobKickoffResponse>("/expand-aliases", { method: "POST", body: JSON.stringify(body) }),
  publishDryRun: (slug: string) =>
    request<PublishDryRun>(`/facilities/${slug}/publish/dry-run`),
  publish: (slug: string, force = false) =>
    request<PublishResponse>(`/facilities/${slug}/publish`, {
      method: "POST",
      body: JSON.stringify({ force }),
    }),
  rerouteEdges: (slug: string, edgeIndices?: number[]) =>
    request<RerouteResponse>(`/facilities/${slug}/reroute-edges`, {
      method: "POST",
      body: JSON.stringify({ edge_indices: edgeIndices ?? null }),
    }),
  saveDepartments: (slug: string, departments: Department[]) =>
    request<{ slug: string; saved_to: string; departments: number }>(
      `/facilities/${slug}/departments`,
      { method: "PUT", body: JSON.stringify({ departments }) },
    ),
  saveMetadata: (slug: string, payload: FacilityMetadataPayload) =>
    request<{ slug: string; saved_to: string; buildings: number; parking: number; transit: number }>(
      `/facilities/${slug}/metadata`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  getOsm: (slug: string) => request<OsmResponse>(`/facilities/${slug}/osm`),
  whoAmI: () => request<WhoAmI>("/auth/me"),
  logout: () => request<{ status: string }>("/auth/logout", { method: "POST" }),
  lockStatus:   (slug: string) => request<LockStatus>(`/facilities/${slug}/lock`),
  lockAcquire:  (slug: string) => request<{ slug: string; held_by: string }>(
    `/facilities/${slug}/lock`, { method: "POST" }),
  lockRelease:  (slug: string) => request<{ slug: string; released: boolean }>(
    `/facilities/${slug}/lock`, { method: "DELETE" }),
  // Proposal lifecycle (contributor flow).
  fork: (slug: string) =>
    request<{ slug: string; author: string; draft_dir: string }>(
      `/facilities/${slug}/fork`, { method: "POST" }),
  getMyDraft: (slug: string) => request<ProposalDraft>(`/proposals/${slug}`),
  saveDraftTopology: (slug: string, topology: Topology) =>
    request<{ slug: string; saved_to: string; nodes: number; edges: number }>(
      `/proposals/${slug}/topology`,
      { method: "PUT", body: JSON.stringify(topology) },
    ),
  saveDraftMetadata: (slug: string, payload: FacilityMetadataPayload) =>
    request<{ slug: string; saved_to: string }>(
      `/proposals/${slug}/metadata`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  saveDraftDepartments: (slug: string, departments: Department[]) =>
    request<{ slug: string; saved_to: string; departments: number }>(
      `/proposals/${slug}/departments`,
      { method: "PUT", body: JSON.stringify({ departments }) },
    ),
  discardDraft: (slug: string) =>
    request<{ slug: string; discarded: boolean }>(
      `/proposals/${slug}`, { method: "DELETE" }),
  submitProposal: (slug: string, message: string) =>
    request<SubmitResponse>(`/facilities/${slug}/submit`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  // Proposal review (admin flow).
  listProposals: () => request<ProposalSummary[]>("/proposals"),
  approveProposal: (slug: string, author: string, force = false) =>
    request<PublishResponse>(
      `/facilities/${slug}/proposals/${author}/approve`,
      { method: "POST", body: JSON.stringify({ force }) },
    ),
  rejectProposal: (slug: string, author: string, reviewNote?: string) =>
    request<{ slug: string; author: string; status: string; review_note: string | null }>(
      `/facilities/${slug}/proposals/${author}/reject`,
      { method: "POST", body: JSON.stringify({ review_note: reviewNote ?? null }) },
    ),
  reloadRoles: () =>
    request<{ admin: string; facility_editors: string[] }>(
      "/admin/roles/reload", { method: "POST" }),
};

export interface OsmFeature {
  name?: string;
  building?: string;
  amenity?: string;
  healthcare?: string;
  shop?: string;
  polygon: [number, number][];
  [key: string]: unknown;
}

export interface OsmResponse {
  slug: string;
  available: boolean;
  features: OsmFeature[];
  /** Each footway is a list of [lat, lng] vertices forming a polyline. */
  footways: [number, number][][];
}

export interface FacilityBuilding {
  name: string;
  lat: number;
  lng: number;
  nearest_buildings?: string[];
  [key: string]: unknown;
}

export interface FacilityParking {
  name: string;
  lat?: number;
  lng?: number;
  nearest_buildings?: string[];
  [key: string]: unknown;
}

export interface FacilityTransit {
  name: string;
  lat?: number;
  lng?: number;
  [key: string]: unknown;
}

export interface FacilityMetadataPayload {
  name: string;
  address?: string;
  type?: string;
  main_phone?: string;
  campus_description?: string;
  buildings: FacilityBuilding[];
  parking: FacilityParking[];
  transit: FacilityTransit[];
}

/** Loose department shape — anything the editor doesn't recognize is preserved. */
export interface Department {
  name: string;
  building?: string;
  floor?: string;
  topology_node_id?: string;
  aliases?: string[];
  hours?: string;
  check_in?: string;
  directions?: string;
  confidence?: string;
  source?: string;
  accessible?: boolean;
  [key: string]: unknown;
}

export interface RerouteResponse {
  slug: string;
  rerouted: { index: number; from: string; to: string; distance_meters: number; walk_minutes: number; geometry_points: number }[];
  skipped: { index: number; reason: string }[];
  topology_path: string;
}

// Keep the old name for back-compat with NewFacilityModal.
export type BootstrapResponse = JobKickoffResponse;

// ----- React hooks -----

export const queryKeys = {
  facilities: ["facilities"] as const,
  facility:   (slug: string) => ["facility", slug] as const,
  suggestions: (slug: string) => ["suggestions", slug] as const,
  edgePhotos: (slug: string, fromId: string, toId: string) =>
    ["edge-photos", slug, fromId, toId] as const,
  nodePhotos: (slug: string, nodeId: string) =>
    ["node-photos", slug, nodeId] as const,
};

export function useWhoAmI() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: api.whoAmI,
    staleTime: 30_000,
  });
}

export function useLockStatus(slug: string | null | undefined) {
  return useQuery({
    queryKey: slug ? ["lock", slug] : ["lock", "none"],
    queryFn: () => {
      if (!slug) throw new Error("useLockStatus called without slug");
      return api.lockStatus(slug);
    },
    enabled: !!slug,
    refetchInterval: 30_000,  // periodic poll so the UI sees holder churn
    staleTime: 5_000,
  });
}

export function useCurrentSettings() {
  return useQuery({
    queryKey: ["settings", "current"],
    queryFn: api.currentSettings,
    staleTime: 60_000,
  });
}

export function useTestConnection() {
  return useMutation({ mutationFn: api.testConnection });
}

export function useFacilities() {
  return useQuery({
    queryKey: queryKeys.facilities,
    queryFn: api.listFacilities,
    select: (data) => data.facilities,
  });
}

export function useFacility(slug: string | null | undefined) {
  // We assert slug presence inside queryFn rather than casting at the top,
  // so a misuse (running with null) crashes loudly instead of hitting /facilities/null.
  return useQuery({
    queryKey: slug ? queryKeys.facility(slug) : ["facility", "none"],
    queryFn: () => {
      if (!slug) throw new Error("useFacility called without a slug");
      return api.getFacility(slug);
    },
    enabled: !!slug,
  });
}

export function useSaveTopology() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, topology }: { slug: string; topology: Topology }) =>
      api.saveTopology(slug, topology),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: queryKeys.facility(slug) });
      qc.invalidateQueries({ queryKey: queryKeys.facilities });
    },
  });
}

export function useBootstrap() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BootstrapRequest) => api.bootstrap(body),
    onSuccess: () => {
      // Invalidate now so the new bootstrap shows up in the grid as soon as
      // the job completes (the modal triggers a refetch then too).
      qc.invalidateQueries({ queryKey: queryKeys.facilities });
    },
  });
}

export function useDraftEdges() {
  return useMutation({ mutationFn: (body: DraftEdgesRequest) => api.draftEdges(body) });
}

export function useStreetviewEdgesBulk() {
  return useMutation({
    mutationFn: (body: StreetviewEdgesRequest) => api.streetviewEdgesBulk(body),
  });
}

export function useSuggestions(slug: string | null | undefined) {
  return useQuery({
    queryKey: slug ? queryKeys.suggestions(slug) : ["suggestions", "none"],
    queryFn: () => {
      if (!slug) throw new Error("useSuggestions called without slug");
      return api.getSuggestions(slug);
    },
    enabled: !!slug,
    staleTime: 10_000,
  });
}

export function useRegenerateSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, fromId, toId, useRouting }: {
      slug: string; fromId: string; toId: string; useRouting?: boolean;
    }) => api.regenerateSuggestion(slug, fromId, toId, useRouting),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: queryKeys.suggestions(slug) });
    },
  });
}

export function useAcceptSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, fromId, toId, replaceGeometry }: {
      slug: string; fromId: string; toId: string; replaceGeometry?: boolean;
    }) => api.acceptSuggestion(slug, fromId, toId, replaceGeometry ?? true),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: queryKeys.suggestions(slug) });
      qc.invalidateQueries({ queryKey: queryKeys.facility(slug) });
    },
  });
}

export function useDiscardSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, fromId, toId }: {
      slug: string; fromId: string; toId: string;
    }) => api.discardSuggestion(slug, fromId, toId),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: queryKeys.suggestions(slug) });
    },
  });
}

// --- Photo edge-walker (docs/29) ---

export function useEdgePhotos(
  slug: string | null | undefined, fromId: string | null | undefined, toId: string | null | undefined,
) {
  const enabled = !!slug && !!fromId && !!toId;
  return useQuery({
    queryKey: enabled ? queryKeys.edgePhotos(slug!, fromId!, toId!) : ["edge-photos", "none"],
    queryFn: () => {
      if (!enabled) throw new Error("useEdgePhotos called with missing args");
      return api.listEdgePhotos(slug!, fromId!, toId!);
    },
    enabled,
    staleTime: 5_000,
  });
}

export function useUploadEdgePhoto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, fromId, toId, file, caption, consent }: {
      slug: string; fromId: string; toId: string;
      file: File; caption: string | null; consent: boolean;
    }) => api.uploadEdgePhoto(slug, fromId, toId, file, caption, consent),
    onSuccess: (_data, { slug, fromId, toId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.edgePhotos(slug, fromId, toId) });
    },
  });
}

export function useReorderEdgePhotos() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, fromId, toId, photoIds }: {
      slug: string; fromId: string; toId: string; photoIds: string[];
    }) => api.reorderEdgePhotos(slug, fromId, toId, photoIds),
    onSuccess: (_data, { slug, fromId, toId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.edgePhotos(slug, fromId, toId) });
    },
  });
}

export function useUpdateEdgePhotoCaption() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, fromId, toId, photoId, caption }: {
      slug: string; fromId: string; toId: string; photoId: string; caption: string | null;
    }) => api.updateEdgePhotoCaption(slug, fromId, toId, photoId, caption),
    onSuccess: (_data, { slug, fromId, toId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.edgePhotos(slug, fromId, toId) });
    },
  });
}

export function useDeleteEdgePhoto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, fromId, toId, photoId }: {
      slug: string; fromId: string; toId: string; photoId: string;
    }) => api.deleteEdgePhoto(slug, fromId, toId, photoId),
    onSuccess: (_data, { slug, fromId, toId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.edgePhotos(slug, fromId, toId) });
    },
  });
}

export function useGenerateFromPhotos() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, fromId, toId }: {
      slug: string; fromId: string; toId: string;
    }) => api.generateFromPhotos(slug, fromId, toId),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: queryKeys.suggestions(slug) });
    },
  });
}

// --- Node photos ---

export function useNodePhotos(slug: string | null | undefined, nodeId: string | null | undefined) {
  const enabled = !!slug && !!nodeId;
  return useQuery({
    queryKey: enabled ? queryKeys.nodePhotos(slug!, nodeId!) : ["node-photos", "none"],
    queryFn: () => {
      if (!enabled) throw new Error("useNodePhotos called with missing args");
      return api.listNodePhotos(slug!, nodeId!);
    },
    enabled,
    staleTime: 5_000,
  });
}

export function useUploadNodePhoto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, nodeId, file, caption, consent }: {
      slug: string; nodeId: string; file: File; caption: string | null; consent: boolean;
    }) => api.uploadNodePhoto(slug, nodeId, file, caption, consent),
    onSuccess: (_data, { slug, nodeId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.nodePhotos(slug, nodeId) });
    },
  });
}

export function useReorderNodePhotos() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, nodeId, photoIds }: {
      slug: string; nodeId: string; photoIds: string[];
    }) => api.reorderNodePhotos(slug, nodeId, photoIds),
    onSuccess: (_data, { slug, nodeId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.nodePhotos(slug, nodeId) });
    },
  });
}

export function useUpdateNodePhotoCaption() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, nodeId, photoId, caption }: {
      slug: string; nodeId: string; photoId: string; caption: string | null;
    }) => api.updateNodePhotoCaption(slug, nodeId, photoId, caption),
    onSuccess: (_data, { slug, nodeId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.nodePhotos(slug, nodeId) });
    },
  });
}

export function useDeleteNodePhoto() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, nodeId, photoId }: {
      slug: string; nodeId: string; photoId: string;
    }) => api.deleteNodePhoto(slug, nodeId, photoId),
    onSuccess: (_data, { slug, nodeId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.nodePhotos(slug, nodeId) });
    },
  });
}

export function useExtractDepartments() {
  return useMutation({ mutationFn: (body: ExtractDepartmentsRequest) => api.extractDepartments(body) });
}

export function useExpandAliases() {
  return useMutation({ mutationFn: (body: ExpandAliasesRequest) => api.expandAliases(body) });
}

export function usePublishDryRun(slug: string | null | undefined) {
  return useQuery({
    queryKey: slug ? ["publish-dry-run", slug] : ["publish-dry-run", "none"],
    queryFn: () => {
      if (!slug) throw new Error("usePublishDryRun called without slug");
      return api.publishDryRun(slug);
    },
    enabled: !!slug,
    staleTime: 5_000,
  });
}

export function useFacilityOsm(slug: string | null | undefined) {
  return useQuery({
    queryKey: slug ? ["facility", slug, "osm"] : ["facility", "none", "osm"],
    queryFn: () => {
      if (!slug) throw new Error("useFacilityOsm called without slug");
      return api.getOsm(slug);
    },
    enabled: !!slug,
    staleTime: 60_000,
  });
}

export function useSaveMetadata() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, payload }: { slug: string; payload: FacilityMetadataPayload }) =>
      api.saveMetadata(slug, payload),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: queryKeys.facility(slug) });
      qc.invalidateQueries({ queryKey: queryKeys.facilities });
    },
  });
}

export function useSaveDepartments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, departments }: { slug: string; departments: Department[] }) =>
      api.saveDepartments(slug, departments),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: queryKeys.facility(slug) });
      qc.invalidateQueries({ queryKey: queryKeys.facilities });
    },
  });
}

export function useRerouteEdges() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, edgeIndices }: { slug: string; edgeIndices?: number[] }) =>
      api.rerouteEdges(slug, edgeIndices),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: queryKeys.facility(slug) });
    },
  });
}

export function usePublish() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, force }: { slug: string; force?: boolean }) => api.publish(slug, force),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: queryKeys.facility(slug) });
      qc.invalidateQueries({ queryKey: queryKeys.facilities });
      qc.invalidateQueries({ queryKey: ["publish-dry-run", slug] });
    },
  });
}

export const proposalKeys = {
  list: ["proposals"] as const,
  draft: (slug: string) => ["proposal-draft", slug] as const,
};

export function useMyProposalDraft(slug: string | null | undefined) {
  return useQuery({
    queryKey: slug ? proposalKeys.draft(slug) : ["proposal-draft", "none"],
    queryFn: () => {
      if (!slug) throw new Error("useMyProposalDraft called without slug");
      return api.getMyDraft(slug);
    },
    enabled: !!slug,
    // Returning null rather than throwing for the "no draft yet" case keeps
    // callers from having to special-case the 404 → "show Fork CTA" flow.
    retry: false,
  });
}

export function useFork() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => api.fork(slug),
    onSuccess: (_data, slug) => {
      qc.invalidateQueries({ queryKey: proposalKeys.draft(slug) });
    },
  });
}

export function useSaveDraftTopology() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, topology }: { slug: string; topology: Topology }) =>
      api.saveDraftTopology(slug, topology),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: proposalKeys.draft(slug) });
    },
  });
}

export function useSaveDraftMetadata() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, payload }: { slug: string; payload: FacilityMetadataPayload }) =>
      api.saveDraftMetadata(slug, payload),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: proposalKeys.draft(slug) });
    },
  });
}

export function useSaveDraftDepartments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, departments }: { slug: string; departments: Department[] }) =>
      api.saveDraftDepartments(slug, departments),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: proposalKeys.draft(slug) });
    },
  });
}

export function useDiscardDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => api.discardDraft(slug),
    onSuccess: (_data, slug) => {
      qc.invalidateQueries({ queryKey: proposalKeys.draft(slug) });
    },
  });
}

export function useSubmitProposal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, message }: { slug: string; message: string }) =>
      api.submitProposal(slug, message),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: proposalKeys.draft(slug) });
      qc.invalidateQueries({ queryKey: proposalKeys.list });
    },
  });
}

export function useProposalsList(opts: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: proposalKeys.list,
    queryFn: api.listProposals,
    enabled: opts.enabled ?? true,
    refetchInterval: 30_000,
    staleTime: 5_000,
  });
}

export function useApproveProposal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, author, force }: { slug: string; author: string; force?: boolean }) =>
      api.approveProposal(slug, author, force ?? false),
    onSuccess: (_data, { slug }) => {
      qc.invalidateQueries({ queryKey: queryKeys.facility(slug) });
      qc.invalidateQueries({ queryKey: queryKeys.facilities });
      qc.invalidateQueries({ queryKey: proposalKeys.list });
    },
  });
}

export function useRejectProposal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      slug,
      author,
      reviewNote,
    }: { slug: string; author: string; reviewNote?: string }) =>
      api.rejectProposal(slug, author, reviewNote),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: proposalKeys.list });
    },
  });
}
