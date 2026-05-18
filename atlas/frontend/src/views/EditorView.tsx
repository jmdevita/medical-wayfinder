import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Sparkles, ArrowRight, Check, Loader2, Plus, Trash2, Maximize2 } from "lucide-react";
import { Route as EditorRoute } from "@/routes/editor";
import type { PublishDryRun } from "@/lib/api";
import {
  ApiError,
  api,
  queryKeys,
  useFacilities,
  useFacility,
  useFacilityOsm,
  useFork,
  useLockStatus,
  useMyProposalDraft,
  useSaveDraftTopology,
  useSaveTopology,
  useDraftEdges,
  usePublishDryRun,
  useRerouteEdges,
  useStreetviewEdgesBulk,
  useSuggestions,
  useWhoAmI,
} from "@/lib/api";
import { TYPE_COLOR, TYPE_LABEL } from "@/lib/topology-meta";
import { useAtlasStore } from "@/lib/store";
import type { AccessibilityFeature, Topology, TopologyEdge, TopologyNode } from "@/lib/types";
import { haversineMeters, polylineMeters, uniqueNodeId, walkMinutes } from "@/lib/topology-helpers";
import type { Department } from "@/lib/api";
import { Field } from "@/components/ui/Field";
import { JobInlineProgress } from "@/components/JobInlineProgress";
import { PublishModal } from "@/components/PublishModal";
import { EdgeInspector } from "@/components/inspectors/EdgeInspector";
import { Section } from "@/components/inspectors/Section";
import { PhotoUploadPanel } from "@/components/PhotoUploadPanel";
import { PALETTE_EVENT } from "@/components/CommandPalette";
import { DepartmentsPanel } from "@/components/editor/DepartmentsPanel";
import { DepartmentPickerModal } from "@/components/editor/DepartmentPickerModal";
import { useDepartmentEditor } from "@/components/editor/useDepartmentEditor";
import { FacilityPanel } from "@/components/editor/FacilityPanel";
import { cn } from "@/lib/utils";

/**
 * Three-state label for the cmd-bar Validate button:
 *   undefined  → "Validate" (neutral, dry-run not run yet)
 *   issues>0   → "N issues"   (ochre)
 *   warnings>0 → "Ready · N warnings"  (ochre)
 *   else       → "Valid"     (moss)
 */
function validateLabel(d: PublishDryRun | undefined): string {
  if (!d) return "Validate";
  if (!d.ok) return `${d.issues.length} issue${d.issues.length === 1 ? "" : "s"}`;
  if (d.warnings.length > 0) {
    return `Ready · ${d.warnings.length} warning${d.warnings.length === 1 ? "" : "s"}`;
  }
  return "Valid";
}

function validateTone(d: PublishDryRun | undefined): "moss" | "ochre" | undefined {
  if (!d) return undefined;
  return !d.ok || d.warnings.length > 0 ? "ochre" : "moss";
}

export function EditorView() {
  const search = EditorRoute.useSearch();
  const { data: facilities } = useFacilities();
  const { data: who } = useWhoAmI();
  const mode: EditorMode = who?.role === "contributor" ? "draft" : "shared";
  // Contributors can only fork published facilities; a fallback to a
  // bootstrap-only entry would dead-end at the Fork CTA with a 404 from
  // /fork. Pick the first published one for them.
  const fallbackSlug = mode === "draft"
    ? facilities?.find((f) => f.status === "published")?.id
    : facilities?.[0]?.id;
  const slug = search.slug ?? fallbackSlug ?? null;

  // Seed the active-facility store from the URL slug so deep links + refreshes
  // light up the TopBar Publish button (which reads from the store).
  const setActiveFacility = useAtlasStore((s) => s.setActiveFacility);
  const activeId = useAtlasStore((s) => s.activeFacility?.id);
  useEffect(() => {
    if (!slug || !facilities) return;
    if (activeId === slug) return;
    const f = facilities.find((x) => x.id === slug);
    if (f) setActiveFacility(f);
  }, [slug, facilities, activeId, setActiveFacility]);

  // Shared workspace path: facility_editor + admin (and dev mode) read from
  // the bootstrap-or-published source. Contributors read from their own
  // personal draft, which only exists after they've forked.
  const facilityQuery = useFacility(mode === "shared" ? slug : null);
  const draftQuery = useMyProposalDraft(mode === "draft" ? slug : null);

  const isPending = mode === "shared" ? facilityQuery.isPending : draftQuery.isPending;
  const isError = mode === "shared" ? facilityQuery.isError : draftQuery.isError;
  const error = mode === "shared" ? facilityQuery.error : draftQuery.error;

  if (!slug || (isPending && !(facilityQuery.data || draftQuery.data))) {
    return <Loading message={slug ? `Loading ${slug}…` : "Discovering facilities…"} />;
  }

  // Contributor without a personal draft yet: 404 surfaces here. Show the
  // Fork CTA instead of a generic error state.
  if (mode === "draft" && isError && (error as ApiError | null)?.status === 404) {
    return <ForkCallToAction slug={slug} />;
  }

  if (isError) {
    return <ErrorState message={(error as Error | null)?.message ?? "Failed to load facility"} />;
  }

  const detail = mode === "shared"
    ? facilityQuery.data
    : (draftQuery.data
        ? {
            facility: draftQuery.data.facility,
            topology: draftQuery.data.topology,
            proposal: draftQuery.data.proposal,
          }
        : undefined);

  if (!detail || !detail.topology) {
    return <NoTopologyState slug={slug} facilityName={(detail?.facility.name as string) ?? slug} />;
  }

  const loadedDetail = {
    facility: detail.facility as { name: string; departments?: unknown[] },
    topology: detail.topology,
  };
  const proposal = mode === "draft"
    ? (draftQuery.data?.proposal ?? null)
    : null;
  return <EditorViewLoaded slug={slug} detail={loadedDetail} mode={mode} proposal={proposal} />;
}

type EditorMode = "shared" | "draft";

function ForkCallToAction({ slug }: { slug: string }) {
  const fork = useFork();
  return (
    <div className="h-full grid place-items-center px-6">
      <div className="max-w-md text-center">
        <div className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron mb-3">
          Read-only · published version
        </div>
        <h2 className="ff-display text-[26px] mb-3">Fork to edit this facility</h2>
        <p className="text-[13px] text-slate leading-relaxed mb-5">
          Atlas keeps the published version safe. Forking copies it into your
          personal draft so you can experiment without affecting other
          contributors. When you're done, submit your changes for the admin
          to review.
        </p>
        <button
          onClick={() => fork.mutate(slug)}
          disabled={fork.isPending}
          className="px-4 h-9 bg-ink text-paper text-[12px] tracking-wide-2 small-caps rounded-sm hover:bg-ink-2 disabled:opacity-60"
        >
          {fork.isPending ? "Forking…" : "Fork to edit"}
        </button>
        {fork.isError && (
          <p className="ff-mono text-[10.5px] text-rust mt-3">
            {(fork.error as Error).message}
          </p>
        )}
      </div>
    </div>
  );
}

function EditorViewLoaded({
  slug,
  detail,
  mode,
  proposal,
}: {
  slug: string;
  detail: { facility: { name: string; departments?: unknown[] }; topology: Topology };
  mode: EditorMode;
  proposal: import("@/lib/api").ProposalSidecar | null;
}) {
  const initialTopology = detail.topology;
  // Local draft buffer — mutations update this, Save flushes via mutation.
  const [draft, _setDraftState] = useState<Topology>(initialTopology);

  // Undo / redo stacks. Refs (not state) so push/pop don't trigger renders;
  // the draft state itself is the only thing that needs to re-render. Capped
  // so a long edit session doesn't grow unboundedly.
  const HISTORY_LIMIT = 50;
  const historyRef = useRef<Topology[]>([]);
  const futureRef = useRef<Topology[]>([]);

  // Wrapped state setter that records the *previous* state in history before
  // applying the next one. Every mutation in this file flows through here.
  // Text-field edits (label/keywords/instruction) push too, so ⌘Z goes
  // letter-by-letter inside text — acceptable; refine later if it becomes
  // friction.
  const setDraft = useCallback<React.Dispatch<React.SetStateAction<Topology>>>((updater) => {
    _setDraftState((prev) => {
      const next = typeof updater === "function"
        ? (updater as (p: Topology) => Topology)(prev)
        : updater;
      if (next === prev) return prev;
      // StrictMode invokes this updater twice in development to surface
      // impure updates. Reference-check the top of history to dedupe so we
      // record one entry per edit, not two.
      if (historyRef.current[historyRef.current.length - 1] !== prev) {
        historyRef.current.push(prev);
        if (historyRef.current.length > HISTORY_LIMIT) historyRef.current.shift();
        futureRef.current = [];
      }
      return next;
    });
  }, []);

  // Reset draft + clear history when the facility changes. Bypasses the
  // history wrapper so the load itself doesn't become an undo step.
  useEffect(() => {
    _setDraftState(initialTopology);
    historyRef.current = [];
    futureRef.current = [];
  }, [initialTopology, slug]);

  const undo = useCallback(() => {
    if (historyRef.current.length === 0) return;
    const prev = historyRef.current.pop()!;
    _setDraftState((cur) => {
      // StrictMode-safe: only push the previous current onto the redo stack
      // if it isn't already there from a double-invocation.
      if (futureRef.current[futureRef.current.length - 1] !== cur) {
        futureRef.current.push(cur);
        if (futureRef.current.length > HISTORY_LIMIT) futureRef.current.shift();
      }
      return prev;
    });
  }, []);

  const redo = useCallback(() => {
    if (futureRef.current.length === 0) return;
    const next = futureRef.current.pop()!;
    _setDraftState((cur) => {
      if (historyRef.current[historyRef.current.length - 1] !== cur) {
        historyRef.current.push(cur);
        if (historyRef.current.length > HISTORY_LIMIT) historyRef.current.shift();
      }
      return next;
    });
  }, []);

  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(initialTopology), [draft, initialTopology]);

  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);
  const layerGroupRef = useRef<L.LayerGroup | null>(null);
  // Supplemental layers driven by toggles (footprints, footways, dept pins).
  const osmGroupRef = useRef<L.LayerGroup | null>(null);
  // Active basemap tile layer; swapped when the satellite toggle flips.
  const tileLayerRef = useRef<L.TileLayer | null>(null);

  const { data: osmData } = useFacilityOsm(slug);

  // Per-facility lock — only meaningful in shared-workspace mode. Contributors
  // operate on their own personal draft, which can't conflict with anyone
  // else's, so they never acquire a lock.
  const { data: lockState } = useLockStatus(mode === "shared" ? slug : null);
  const { data: who } = useWhoAmI();
  // Only acquire when we're actually allowed to: dev mode (auth off) or signed in,
  // AND we're in shared-workspace mode (admin/facility_editor).
  const canAcquireLock =
    mode === "shared" &&
    !!slug &&
    !!who &&
    (!who.auth_enforced || who.authenticated);
  useEffect(() => {
    if (!canAcquireLock || !slug) return;
    let cancelled = false;
    api.lockAcquire(slug).catch(() => {/* surfaced via lockState query */});
    const heartbeat = setInterval(() => {
      if (!cancelled) api.lockAcquire(slug).catch(() => {});
    }, 60_000);
    return () => {
      cancelled = true;
      clearInterval(heartbeat);
      api.lockRelease(slug).catch(() => {});
    };
  }, [slug, canAcquireLock]);

  const lockedByOther =
    !!lockState?.locked &&
    !!who &&
    !!lockState.held_by &&
    lockState.held_by !== who.login &&
    who.login !== "dev";

  const selected     = useAtlasStore((s) => s.selectedNodeId);
  const setSelected  = useAtlasStore((s) => s.setSelectedNodeId);
  const selectedEdgeKey = useAtlasStore((s) => s.selectedEdgeKey);
  const setSelectedEdgeKey = useAtlasStore((s) => s.setSelectedEdgeKey);
  const layers       = useAtlasStore((s) => s.layers);
  const tool         = useAtlasStore((s) => s.editorTool);
  const setTool      = useAtlasStore((s) => s.setEditorTool);
  const toggleLayer  = useAtlasStore((s) => s.toggleLayer);

  // Different mutation per mode — contributors save into their personal
  // draft path, facility_editor/admin save into the shared bootstrap dir.
  // Both hooks are called unconditionally so React's rules of hooks aren't
  // violated; only one is wired into the Save button.
  const sharedSave = useSaveTopology();
  const draftSave = useSaveDraftTopology();
  const saveMutation = mode === "draft" ? draftSave : sharedSave;
  const draftEdges = useDraftEdges();
  const streetviewBulk = useStreetviewEdgesBulk();
  const suggestionsQuery = useSuggestions(mode === "shared" ? slug : null);
  const reroute = useRerouteEdges();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [draftEdgesJobId, setDraftEdgesJobId] = useState<string | null>(null);
  const [streetviewJobId, setStreetviewJobId] = useState<string | null>(null);
  const [publishOpen, setPublishOpen] = useState(false);
  const dryRun = usePublishDryRun(slug);

  // While in addEdge mode, the first clicked node is the start.
  const [edgeStartId, setEdgeStartId] = useState<string | null>(null);

  // Transient feedback (e.g. "edge already exists"). Auto-clears after 2.5s.
  const [flash, setFlash] = useState<string | null>(null);
  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 2500);
    return () => clearTimeout(t);
  }, [flash]);

  // drawEdge mode: in-flight waypoints between the start node and the next
  // node click. Held in a ref so the map mousemove/click handlers can mutate
  // them without forcing the marker-binding effect to rerun on every nudge.
  const waypointsRef = useRef<Array<[number, number]>>([]);
  // Bumping this re-renders the in-flight ghost line via the dedicated effect.
  const [waypointVersion, setWaypointVersion] = useState(0);

  // Right-panel mode: per-node inspector, department management, or facility metadata.
  const [inspectorTab, setInspectorTab] = useState<"node" | "departments" | "facility">("node");

  // Department-assign workflow: panel sets `assigningNames` (an array — supports
  // single Assign on a row OR a bulk-by-floor mapping action), the next node
  // click sets `pendingAssignNodeId`, the panel consumes it and clears both.
  const [assigningNames, setAssigningNames] = useState<string[] | null>(null);
  const [pendingAssignNodeId, setPendingAssignNodeId] = useState<string | null>(null);
  const assigningRef = useRef<string[] | null>(null);
  useEffect(() => { assigningRef.current = assigningNames; }, [assigningNames]);
  // Inline node-side picker.
  const [pickerOpen, setPickerOpen] = useState(false);

  // Lifted dept editor state — owned by EditorView so both DepartmentsPanel
  // and the node-side DepartmentPickerModal can dispatch into the same drafts.
  const initialDepartments = useMemo(
    () => (detail.facility.departments as Department[] | undefined) ?? [],
    [detail.facility.departments],
  );
  const deptController = useDepartmentEditor(slug, initialDepartments);

  // Inline keyword-add state per-node (only one input visible at a time).
  const [keywordDraft, setKeywordDraft] = useState("");

  // Refs that map handlers can read without recreating their event listeners.
  const draftRef = useRef(draft);
  const toolRef = useRef(tool);
  const edgeStartRef = useRef(edgeStartId);
  useEffect(() => { draftRef.current = draft; }, [draft]);
  useEffect(() => { toolRef.current = tool; }, [tool]);
  useEffect(() => { edgeStartRef.current = edgeStartId; }, [edgeStartId]);

  // Reset the in-progress edge (start node + any waypoints) whenever the tool
  // changes away from addEdge.
  useEffect(() => {
    if (tool !== "addEdge") {
      setEdgeStartId(null);
      waypointsRef.current = [];
      setWaypointVersion((v) => v + 1);
    }
  }, [tool]);

  // Clear pending department assignment when leaving the Departments tab so a
  // stray node click after navigation doesn't apply retroactively.
  useEffect(() => {
    if (inspectorTab !== "departments") {
      setAssigningNames(null);
      setPendingAssignNodeId(null);
    }
  }, [inspectorTab]);

  // Pick a default selected node when the facility changes; honor the URL's
  // ?node= deep-link if it refers to a real node in the current topology.
  const searchedNodeId = EditorRoute.useSearch().node;
  useEffect(() => {
    if (!draft.nodes.length) return;
    // While an edge is selected, leave node selection cleared. Otherwise this
    // effect would race with setSelectedEdgeKey (which clears the node) and
    // immediately re-pick the first node, undoing the edge selection.
    if (selectedEdgeKey) return;
    if (searchedNodeId && draft.nodes.some((n) => n.id === searchedNodeId) && selected !== searchedNodeId) {
      setSelected(searchedNodeId);
      return;
    }
    const stillExists = draft.nodes.some((n) => n.id === selected);
    if (!stillExists) setSelected(draft.nodes[0].id);
  }, [draft, selected, selectedEdgeKey, setSelected, searchedNodeId]);

  // ---- mutations on the local draft -----------------------------------

  const addNodeAt = useCallback((lat: number, lng: number) => {
    setDraft((d) => {
      const id = uniqueNodeId(d.nodes);
      const newNode: TopologyNode = {
        id, type: "landmark", label: id, description: "", keywords: [], lat, lng,
      };
      return { ...d, nodes: [...d.nodes, newNode] };
    });
  }, []);

  const moveNode = useCallback((id: string, lat: number, lng: number) => {
    setDraft((d) => ({
      ...d,
      nodes: d.nodes.map((n) => (n.id === id ? { ...n, lat, lng } : n)),
      edges: d.edges.map((e) => {
        if (e.from !== id && e.to !== id) return e;
        const a = e.from === id ? { lat, lng } : d.nodes.find((n) => n.id === e.from);
        const b = e.to   === id ? { lat, lng } : d.nodes.find((n) => n.id === e.to);
        if (!a || !b) return e;
        const dist = haversineMeters(a, b);
        const next: TopologyEdge = {
          ...e,
          distance_meters: dist,
          walk_minutes: walkMinutes(dist),
        };
        // Preserve the routed footway geometry — replace only the dragged
        // endpoint vertex so the curve still wraps the buildings, then mark
        // the edge as stale so the user can re-route via /reroute-edges.
        if (e.geometry && e.geometry.length >= 2) {
          const newGeom = [...e.geometry] as [number, number][];
          if (e.from === id) newGeom[0] = [lat, lng];
          else               newGeom[newGeom.length - 1] = [lat, lng];
          next.geometry = newGeom;
          next.stale_geometry = true;
        }
        return next;
      }),
    }));
  }, []);

  // Returns "created" | "duplicate" | "self" | "missing" so callers can flash
  // the user when the click was a no-op. Pass `waypoints` (ordered intermediate
  // [lat, lng] picks, exclusive of the endpoints) for a curved edge. Geometry
  // is bookended with the node coordinates so the existing drag-rewrite path
  // (replace first/last vertex) keeps working.
  type AddEdgeResult = "created" | "duplicate" | "self" | "missing";
  const addEdgeBetween = useCallback(
    (fromId: string, toId: string, waypoints: Array<[number, number]> = []): AddEdgeResult => {
      if (fromId === toId) return "self";
      const d0 = draftRef.current;
      const dup = d0.edges.some(
        (e) =>
          (e.from === fromId && e.to === toId) || (e.from === toId && e.to === fromId),
      );
      if (dup) return "duplicate";
      const a = d0.nodes.find((n) => n.id === fromId);
      const b = d0.nodes.find((n) => n.id === toId);
      if (!a || !b) return "missing";

      const geometry: Array<[number, number]> | undefined = waypoints.length
        ? [[a.lat, a.lng], ...waypoints, [b.lat, b.lng]]
        : undefined;
      const dist = geometry ? polylineMeters(geometry) : haversineMeters(a, b);
      const newEdge: TopologyEdge = {
        from: fromId,
        to: toId,
        distance_meters: dist,
        walk_minutes: walkMinutes(dist),
        instruction: "",
        blocked: false,
        ...(geometry ? { geometry } : {}),
      };
      setDraft((d) => ({ ...d, edges: [...d.edges, newEdge] }));
      return "created";
    },
    [],
  );

  // Helper: read a friendly node label for flash messages.
  const labelFor = useCallback((id: string) => {
    return draftRef.current.nodes.find((n) => n.id === id)?.label ?? id;
  }, []);

  // Apply an AddEdgeResult: surface a transient banner on duplicates and
  // self-edge clicks; nothing on success.
  const flashAddEdge = useCallback(
    (result: AddEdgeResult, fromId: string, toId: string) => {
      if (result === "duplicate") {
        setFlash(`Edge already exists between ${labelFor(fromId)} and ${labelFor(toId)}`);
      } else if (result === "self") {
        setFlash("Can't draw an edge from a node to itself");
      }
    },
    [labelFor],
  );

  const deleteNode = useCallback((id: string) => {
    // Cascade-delete photos for this node and any edges incident to it so
    // we don't leave orphaned dirs on disk after the topology save.
    const incident = draftRef.current.edges.filter(
      (e) => e.from === id || e.to === id,
    );
    api.deleteAllNodePhotos(slug, id).catch(() => { /* best-effort */ });
    incident.forEach((e) => {
      api.deleteAllEdgePhotos(slug, e.from, e.to).catch(() => { /* best-effort */ });
    });
    setDraft((d) => ({
      ...d,
      nodes: d.nodes.filter((n) => n.id !== id),
      edges: d.edges.filter((e) => e.from !== id && e.to !== id),
    }));
  }, [slug]);

  const updateEdgeInstruction = useCallback((edgeIdx: number, instruction: string) => {
    setDraft((d) => ({
      ...d,
      edges: d.edges.map((e, i) => (i === edgeIdx ? { ...e, instruction } : e)),
    }));
  }, []);

  const updateEdgeFeatures = useCallback(
    (edgeIdx: number, features: AccessibilityFeature[]) => {
      setDraft((d) => ({
        ...d,
        edges: d.edges.map((e, i) =>
          i === edgeIdx
            ? { ...e, accessibility_features: features.length ? features : undefined }
            : e,
        ),
      }));
    },
    [],
  );

  const deleteEdgeAt = useCallback((edgeIdx: number) => {
    const e = draftRef.current.edges[edgeIdx];
    if (e) {
      api.deleteAllEdgePhotos(slug, e.from, e.to).catch(() => { /* best-effort */ });
    }
    setDraft((d) => ({
      ...d,
      edges: d.edges.filter((_, i) => i !== edgeIdx),
    }));
  }, [slug]);

  const clearAllEdges = useCallback(() => {
    setDraft((d) => ({ ...d, edges: [] }));
  }, []);

  // Keyboard shortcuts.
  // - Without modifier: V (select), N (addNode), E (addEdge), Esc (cancel)
  // - ⌘/Ctrl + Enter: open Publish modal
  // - ⌘/Ctrl + S: save (when dirty)
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      const tag = (ev.target as HTMLElement | null)?.tagName;
      const inField = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

      if ((ev.metaKey || ev.ctrlKey) && ev.key === "Enter") {
        ev.preventDefault();
        setPublishOpen(true);
        return;
      }
      if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "s") {
        ev.preventDefault();
        // Topology is saved here when on the Node tab; the Departments and
        // Facility panels listen for the same event and save their own drafts.
        // (Conditional renders ensure only one panel is mounted at a time.)
        window.dispatchEvent(new Event(PALETTE_EVENT.save));
        if (inspectorTab === "node" && dirty) {
          saveMutation.mutate({ slug, topology: draft });
        }
        return;
      }
      if (inField) return;
      // ⌘Z / Ctrl+Z → undo, ⌘⇧Z (or Ctrl+Y) → redo. Skipped when focus is in
      // an input/textarea so native field undo still works there.
      if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "z") {
        ev.preventDefault();
        if (ev.shiftKey) redo();
        else undo();
        return;
      }
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "y") {
        ev.preventDefault();
        redo();
        return;
      }
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      const key = ev.key.toLowerCase();
      // Backspace pops a waypoint while building a curved edge.
      if (key === "backspace" && toolRef.current === "addEdge") {
        if (waypointsRef.current.length > 0) {
          waypointsRef.current = waypointsRef.current.slice(0, -1);
          setWaypointVersion((v) => v + 1);
          ev.preventDefault();
        }
        return;
      }
      if      (key === "v") setTool("select");
      else if (key === "n") setTool("addNode");
      else if (key === "e") setTool("addEdge");
      else if (key === "escape") {
        setEdgeStartId(null);
        setAssigningNames(null);
        waypointsRef.current = [];
        setWaypointVersion((v) => v + 1);
        setTool("select");
      } else return;
      ev.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setTool, dirty, slug, draft, saveMutation, inspectorTab, undo, redo]);

  // Listen for command-palette intents that need editor-local context. Save
  // is already wired through the existing "atlas:save-current-tab" event on
  // each panel; here we only need Validate and Publish.
  useEffect(() => {
    const openValidate = () => {
      qc.invalidateQueries({ queryKey: ["publish-dry-run", slug] });
      setPublishOpen(true);
    };
    const openPublish = () => setPublishOpen(true);
    const onUndo = () => undo();
    const onRedo = () => redo();
    window.addEventListener(PALETTE_EVENT.validate, openValidate);
    window.addEventListener(PALETTE_EVENT.publish, openPublish);
    window.addEventListener(PALETTE_EVENT.undo, onUndo);
    window.addEventListener(PALETTE_EVENT.redo, onRedo);
    return () => {
      window.removeEventListener(PALETTE_EVENT.validate, openValidate);
      window.removeEventListener(PALETTE_EVENT.publish, openPublish);
      window.removeEventListener(PALETTE_EVENT.undo, onUndo);
      window.removeEventListener(PALETTE_EVENT.redo, onRedo);
    };
  }, [qc, slug, undo, redo]);

  // Initial map mount + center on this facility, plus a click handler that
  // dispatches based on the current tool.
  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;
    const center = computeCenter(draft.nodes);
    const m = L.map(mapRef.current, { zoomControl: true }).setView(center, 17);
    const tile = L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}{r}.png", {
      maxZoom: 20,
      subdomains: "abcd",
      attribution: "© OpenStreetMap · CARTO",
    }).addTo(m);
    tileLayerRef.current = tile;

    // Stack layers explicitly: footprints/footways under topology, dept pins
    // over topology. Default overlayPane is z-index 400; we sandwich it.
    m.createPane("atlasOsmPane");
    m.getPane("atlasOsmPane")!.style.zIndex = "380";
    m.createPane("atlasDeptPane");
    m.getPane("atlasDeptPane")!.style.zIndex = "440";

    m.on("click", (ev) => {
      const t = toolRef.current;
      if (t === "addNode") {
        addNodeAt(ev.latlng.lat, ev.latlng.lng);
        return;
      }
      if (t === "addEdge" && edgeStartRef.current) {
        // Empty-map click while we have a start node → append a waypoint.
        // The next node click commits the polyline as the edge geometry.
        waypointsRef.current = [
          ...waypointsRef.current,
          [ev.latlng.lat, ev.latlng.lng] as [number, number],
        ];
        setWaypointVersion((v) => v + 1);
        return;
      }
      // Clicking empty map in select / addEdge-without-start clears state.
      setSelected(null);
      setEdgeStartId(null);
      waypointsRef.current = [];
      setWaypointVersion((v) => v + 1);
    });

    mapInstance.current = m;
    return () => {
      m.remove();
      mapInstance.current = null;
    };
  // Map is mounted exactly once per editor instance; handlers read from refs.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Swap the basemap tile layer when the satellite toggle flips.
  useEffect(() => {
    const m = mapInstance.current;
    if (!m) return;
    const url = layers.satellite
      ? "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
      : "https://{s}.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}{r}.png";
    const attribution = layers.satellite
      ? "Tiles © Esri"
      : "© OpenStreetMap · CARTO";
    if (tileLayerRef.current) tileLayerRef.current.remove();
    tileLayerRef.current = L.tileLayer(url, {
      maxZoom: 20,
      subdomains: layers.satellite ? "" : "abcd",
      attribution,
    }).addTo(m);
  }, [layers.satellite]);

  // Render OSM polygons + footways + department pins in their own group so
  // they can refresh independently of the topology layer.
  useEffect(() => {
    const m = mapInstance.current;
    if (!m) return;
    osmGroupRef.current?.remove();
    const lg = L.layerGroup().addTo(m);
    osmGroupRef.current = lg;

    if (layers.osmFootprints && osmData?.features?.length) {
      for (const feat of osmData.features) {
        if (!Array.isArray(feat.polygon) || feat.polygon.length < 3) continue;
        const isParking = feat.amenity === "parking" || feat.building === "parking";
        L.polygon(feat.polygon, {
          pane: "atlasOsmPane",
          color: "#928D82",
          weight: 0.8,
          fillColor: isParking ? "#DAD2BC" : "#E5DCC4",
          fillOpacity: 0.65,
          dashArray: "2 3",
          interactive: false,
        }).addTo(lg);
      }
    }

    if (layers.footways && osmData?.footways?.length) {
      for (const way of osmData.footways) {
        if (!Array.isArray(way) || way.length < 2) continue;
        L.polyline(way, {
          pane: "atlasOsmPane",
          color: "#1E3A5F",
          weight: 1,
          opacity: 0.45,
          interactive: false,
        }).addTo(lg);
      }
    }

    if (layers.departments) {
      const depts = (detail.facility.departments as Department[] | undefined) ?? [];
      const counts = new Map<string, number>();
      for (const d of depts) {
        const id = d.topology_node_id;
        if (!id) continue;
        counts.set(id, (counts.get(id) ?? 0) + 1);
      }
      for (const [nodeId, count] of counts) {
        const node = draft.nodes.find((n) => n.id === nodeId);
        if (!node) continue;
        L.circleMarker([node.lat, node.lng], {
          pane: "atlasDeptPane",
          radius: 4,
          color: "#F4EFE5",
          weight: 1.5,
          fillColor: "#5B3A4E",
          fillOpacity: 0.95,
          interactive: false,
        }).addTo(lg);
        if (count > 1) {
          L.marker([node.lat, node.lng], {
            pane: "atlasDeptPane",
            icon: L.divIcon({
              className: "atlas-dept-count",
              html: `<span style="display:inline-block;background:#5B3A4E;color:#F4EFE5;border-radius:9px;padding:1px 5px;font-size:9px;font-family:Geist Mono,monospace;letter-spacing:0.04em">×${count}</span>`,
              iconSize: [20, 14],
              iconAnchor: [-6, -6],
            }),
            interactive: false,
          }).addTo(lg);
        }
      }
    }
  }, [layers.osmFootprints, layers.footways, layers.departments, osmData, draft.nodes, detail.facility.departments]);

  // Refit the map to the topology bounds — only when the facility itself
  // changes. Read latest nodes from a ref so dragging a node (which mutates
  // draft.nodes) doesn't yank the user back to a wide view.
  const draftNodesRef = useRef(draft.nodes);
  useEffect(() => { draftNodesRef.current = draft.nodes; }, [draft.nodes]);

  useEffect(() => {
    if (!mapInstance.current) return;
    const nodes = draftNodesRef.current;
    if (!nodes.length) return;
    const bounds = L.latLngBounds(nodes.map((n) => [n.lat, n.lng] as [number, number]));
    mapInstance.current.fitBounds(bounds, { padding: [60, 60], maxZoom: 18 });
  }, [slug]);

  // Imperative "frame all nodes" — wired to a small icon button on the map.
  const frameAll = useCallback(() => {
    if (!mapInstance.current) return;
    const nodes = draftNodesRef.current;
    if (!nodes.length) return;
    const bounds = L.latLngBounds(nodes.map((n) => [n.lat, n.lng] as [number, number]));
    mapInstance.current.fitBounds(bounds, { padding: [60, 60], maxZoom: 18 });
  }, []);

  // In-flight edge preview ("ghost line") — saffron polyline from the start
  // node through any committed waypoints to the cursor. Becomes the edge's
  // geometry on the closing node click (or just a straight edge if there are
  // no waypoints). Solid when waypoints exist, dashed when it's still a
  // straight line from start to cursor.
  const ghostLineRef = useRef<L.Polyline | null>(null);
  useEffect(() => {
    const m = mapInstance.current;
    if (!m) return;

    function onMove(ev: L.LeafletMouseEvent) {
      const start = edgeStartRef.current;
      if (!start || !ghostLineRef.current) return;
      const startNode = draftRef.current.nodes.find((n) => n.id === start);
      if (!startNode) return;
      ghostLineRef.current.setLatLngs([
        [startNode.lat, startNode.lng],
        ...waypointsRef.current,
        [ev.latlng.lat, ev.latlng.lng],
      ]);
    }

    const cleanup = () => {
      if (ghostLineRef.current) {
        ghostLineRef.current.remove();
        ghostLineRef.current = null;
      }
      m.off("mousemove", onMove);
    };

    if (tool === "addEdge" && edgeStartId) {
      const startNode = draft.nodes.find((n) => n.id === edgeStartId);
      if (!startNode) return cleanup;
      const hasWaypoints = waypointsRef.current.length > 0;
      const ghost = L.polyline(
        [[startNode.lat, startNode.lng], ...waypointsRef.current],
        {
          color: "#B8530A",
          weight: hasWaypoints ? 3 : 2,
          opacity: 0.85,
          dashArray: hasWaypoints ? undefined : "5 5",
          interactive: false,
        },
      ).addTo(m);
      ghostLineRef.current = ghost;
      m.on("mousemove", onMove);
    }

    return cleanup;
  }, [tool, edgeStartId, waypointVersion, draft.nodes]);

  // Render nodes + edges every time the draft or selection changes.
  useEffect(() => {
    const m = mapInstance.current;
    if (!m) return;
    layerGroupRef.current?.remove();
    const lg = L.layerGroup().addTo(m);
    layerGroupRef.current = lg;

    if (layers.topology) {
      draft.edges.forEach((e, edgeIdx) => {
        const a = draft.nodes.find((n) => n.id === e.from);
        const b = draft.nodes.find((n) => n.id === e.to);
        if (!a || !b) return;
        const isEmpty = !e.instruction;
        const isStale = e.stale_geometry === true;
        const involves = e.from === selected || e.to === selected;
        const edgeKey = `${e.from}__${e.to}`;
        const isSelectedEdge = edgeKey === selectedEdgeKey;
        const latlngs = (e.geometry?.length ? e.geometry : [[a.lat, a.lng], [b.lat, b.lng]]) as [number, number][];
        // Style precedence: selected-edge > selected-node-incident > stale > empty > authored.
        const color  = isSelectedEdge ? "#913F08" : involves ? "#B8530A" : isStale ? "#D87125" : isEmpty ? "#A98024" : "#3A352E";
        const weight = isSelectedEdge ? 5 : involves ? 4 : 2.5;
        const dashArray = isStale ? "4 4" : isEmpty && !isSelectedEdge ? "6 5" : undefined;
        const poly = L.polyline(latlngs, {
          color,
          weight,
          opacity: 0.95,
          dashArray,
        }).addTo(lg);
        // Tag the polyline so the drag handler can update incident edges live.
        (poly as L.Polyline & { _edgeFrom?: string; _edgeTo?: string })._edgeFrom = e.from;
        (poly as L.Polyline & { _edgeFrom?: string; _edgeTo?: string })._edgeTo = e.to;
        // Left-click an edge in select mode → select it (clears node selection
        // via the store's mutually-exclusive setter). The EdgeInspector then
        // takes over the right panel.
        poly.on("click", (ev) => {
          L.DomEvent.stop(ev as unknown as L.LeafletEvent);
          if (toolRef.current !== "select") return;
          setSelectedEdgeKey(edgeKey);
        });
        // Right-click in select mode → confirm + delete (kept as a quick path;
        // the inspector also has a Danger zone).
        poly.on("contextmenu", (ev) => {
          L.DomEvent.stop(ev as unknown as L.LeafletEvent);
          if (toolRef.current !== "select") return;
          const fromLabel = a.label;
          const toLabel = b.label;
          if (confirm(`Delete edge between ${fromLabel} and ${toLabel}?`)) {
            deleteEdgeAt(edgeIdx);
          }
        });
      });

      draft.nodes.forEach((n) => {
        const isSel = n.id === selected;
        const isEdgeStart = n.id === edgeStartId;
        const highlight = isSel || isEdgeStart;
        const marker = L.circleMarker([n.lat, n.lng], {
          radius: highlight ? 11 : 7,
          color: highlight ? "#B8530A" : "#F4EFE5",
          weight: highlight ? 3 : 2,
          fillColor: TYPE_COLOR[n.type],
          fillOpacity: 1,
        }).addTo(lg);
        marker.bindTooltip(n.label, {
          permanent: true,
          direction: "top",
          offset: [0, -10],
          className: "atlas-tt",
        });

        // ---- right-click: delete node (in addNode mode only) ----
        marker.on("contextmenu", (ev) => {
          L.DomEvent.stop(ev as unknown as L.LeafletEvent);
          if (toolRef.current !== "addNode") return;
          const incident = draftRef.current.edges.filter(
            (e) => e.from === n.id || e.to === n.id,
          ).length;
          const tail = incident
            ? ` and ${incident} incident edge${incident === 1 ? "" : "s"}`
            : "";
          if (confirm(`Delete node "${n.label}"${tail}?`)) {
            deleteNode(n.id);
          }
        });

        // ---- click: tool-aware ----
        marker.on("click", (ev) => {
          L.DomEvent.stop(ev as unknown as L.LeafletEvent);
          // Assignment mode (Departments panel asked us to pick a node).
          if (assigningRef.current) {
            setPendingAssignNodeId(n.id);
            return;
          }
          const t = toolRef.current;
          if (t === "addEdge") {
            const start = edgeStartRef.current;
            if (!start) {
              setEdgeStartId(n.id);
              waypointsRef.current = [];
              setWaypointVersion((v) => v + 1);
              return;
            }
            if (start === n.id) {
              // Same node clicked twice → cancel the in-flight edge.
              setEdgeStartId(null);
              waypointsRef.current = [];
              setWaypointVersion((v) => v + 1);
              return;
            }
            // No waypoints → straight edge. With waypoints → curved edge with
            // explicit geometry through each pick.
            const result = addEdgeBetween(start, n.id, waypointsRef.current);
            flashAddEdge(result, start, n.id);
            setEdgeStartId(null);
            waypointsRef.current = [];
            setWaypointVersion((v) => v + 1);
            return;
          }
          // select mode (or addNode click on a node — treat as select)
          setSelected(n.id);
        });

        // ---- drag in select mode ----
        marker.on("mousedown", (ev) => {
          if (toolRef.current !== "select" || !m) return;
          L.DomEvent.stop(ev as unknown as L.LeafletEvent);
          m.dragging.disable();

          let lastLat = n.lat;
          let lastLng = n.lng;

          // Snapshot incident edges at drag-start so we can rewrite their
          // latlngs cheaply in mousemove. We preserve any routed footway
          // geometry — only the very first or last vertex follows the cursor
          // so the curve through the buildings stays intact (just kinks at
          // the moved end).
          type LiveEdge = {
            poly: L.Polyline;
            isFrom: boolean;
            // The mid-vertices of the polyline (everything except the moving
            // endpoint). Pre-baked to a fresh array on drag-start.
            preserved: [number, number][];
          };
          const incident: LiveEdge[] = [];
          if (layerGroupRef.current) {
            layerGroupRef.current.eachLayer((layer) => {
              const poly = layer as L.Polyline & { _edgeFrom?: string; _edgeTo?: string };
              if (poly._edgeFrom === undefined) return;
              if (poly._edgeFrom !== n.id && poly._edgeTo !== n.id) return;
              const isFrom = poly._edgeFrom === n.id;
              const otherId = isFrom ? poly._edgeTo : poly._edgeFrom;
              const other = draftRef.current.nodes.find((nn) => nn.id === otherId);
              if (!other) return;
              const edgeMatch = draftRef.current.edges.find(
                (ee) => ee.from === poly._edgeFrom && ee.to === poly._edgeTo,
              );
              // Geometry is the source of truth for visual shape if it exists,
              // else two-point straight line.
              const fullGeom = (edgeMatch?.geometry?.length
                ? edgeMatch.geometry
                : [[n.lat, n.lng], [other.lat, other.lng]]) as [number, number][];
              const preserved: [number, number][] = isFrom
                ? fullGeom.slice(1)            // keep middle..end fixed
                : fullGeom.slice(0, -1);       // keep start..middle fixed
              incident.push({ poly, isFrom, preserved });
            });
          }

          const onMove = (mEv: L.LeafletMouseEvent) => {
            lastLat = mEv.latlng.lat;
            lastLng = mEv.latlng.lng;
            marker.setLatLng(mEv.latlng);
            for (const ie of incident) {
              ie.poly.setLatLngs(
                ie.isFrom
                  ? [[lastLat, lastLng], ...ie.preserved]
                  : [...ie.preserved, [lastLat, lastLng]],
              );
            }
          };
          const onUp = () => {
            m.off("mousemove", onMove);
            m.off("mouseup", onUp);
            m.dragging.enable();
            // Commit only if the position actually moved.
            if (lastLat !== n.lat || lastLng !== n.lng) {
              moveNode(n.id, lastLat, lastLng);
            }
          };
          m.on("mousemove", onMove);
          m.on("mouseup", onUp);
        });
      });
    }
  }, [draft, selected, selectedEdgeKey, edgeStartId, layers, setSelected, setSelectedEdgeKey, addEdgeBetween, flashAddEdge, deleteEdgeAt, moveNode]);

  const sel = draft.nodes.find((n) => n.id === selected) ?? null;
  const selectedEdge = (() => {
    if (!selectedEdgeKey) return null;
    const [from, to] = selectedEdgeKey.split("__");
    const idx = draft.edges.findIndex((e) => e.from === from && e.to === to);
    return idx >= 0 ? { edge: draft.edges[idx], idx } : null;
  })();
  const incidentEdges = sel
    ? draft.edges.filter((e) => e.from === sel.id || e.to === sel.id)
    : [];
  const emptyEdges = draft.edges.filter((e) => !e.instruction).length;
  const staleEdgeIndices = useMemo(
    () => draft.edges.map((e, i) => (e.stale_geometry ? i : -1)).filter((i) => i >= 0),
    [draft.edges],
  );
  // Read from the lifted draft state so newly-mapped depts (via picker or
  // map-click) show up in the node panel immediately, even before the
  // editor saves the dept changes.
  const departments = deptController.drafts.filter(
    (d) => d.topology_node_id === sel?.id,
  );

  const updateNode = (id: string, patch: Partial<TopologyNode>) => {
    setDraft((d) => ({
      ...d,
      nodes: d.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
    }));
  };

  return (
    <div className="h-full flex bg-paper">
      {/* Layers rail */}
      <aside className="w-[240px] border-r border-hairline bg-paper overflow-y-auto px-4 py-5">
        <PanelHeader num="01" title="Layers" />
        <div className="space-y-1.5 mb-7">
          <LayerRow label="OSM building footprints"  on={layers.osmFootprints}  toggle={() => toggleLayer("osmFootprints")} swatch="#E5DCC4" />
          <LayerRow label="Topology · nodes & edges" on={layers.topology}       toggle={() => toggleLayer("topology")}       swatch="#B8530A" />
          <LayerRow label="Department pins"          on={layers.departments}    toggle={() => toggleLayer("departments")}    swatch="#5B3A4E" />
          <LayerRow label="OSM footways"             on={layers.footways}       toggle={() => toggleLayer("footways")}       swatch="#1E3A5F" />
          <LayerRow label="Satellite basemap"        on={layers.satellite}      toggle={() => toggleLayer("satellite")}      swatch="#928D82" />
        </div>

        <PanelHeader num="02" title="Tools" />
        <div className="grid grid-cols-3 gap-1.5 mb-7">
          {(["select", "addNode", "addEdge"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTool(t)}
              className={cn(
                "px-2 h-9 text-[10.5px] tracking-wide-2 small-caps rounded-sm border transition-colors",
                tool === t ? "bg-ink text-paper border-ink" : "border-hairline text-slate hover:text-ink hover:border-ink",
              )}
              title={
                t === "addEdge"
                  ? "Click two nodes for a straight edge · click empty map between them to add waypoints (curved)"
                  : undefined
              }
            >
              {t === "select" ? "Select" : t === "addNode" ? "Node" : "Edge"}
            </button>
          ))}
        </div>

        <PanelHeader num="03" title="Health" />
        <div className="space-y-2 text-[11.5px]">
          <HealthRow label="Validator"          value="Passing"                                         tone="moss" />
          <HealthRow label="Empty edges"        value={`${emptyEdges} of ${draft.edges.length}`}        tone={emptyEdges > 0 ? "ochre" : "moss"} />
          <HealthRow label="Stale geometry"     value={String(staleEdgeIndices.length)}                  tone={staleEdgeIndices.length > 0 ? "ochre" : "moss"} />
          <HealthRow label="Total nodes"        value={String(draft.nodes.length)}                       tone="ink" />
          <HealthRow label="Departments mapped" value={String((detail.facility.departments as unknown[] | undefined)?.length ?? 0)} tone="ink" />
        </div>

        {mode === "shared" && (
          <>
        <button
          disabled={!!draftEdgesJobId || draftEdges.isPending || dirty}
          onClick={async () => {
            try {
              const res = await draftEdges.mutateAsync({ slug, max_dist: 800 });
              setDraftEdgesJobId(res.job_id);
            } catch {
              // Mutation error is rendered by JobInlineProgress when it has a job;
              // the synchronous case (e.g. validation 422) shows the toast below.
            }
          }}
          className={cn(
            "mt-6 w-full h-10 rounded-sm text-[11.5px] tracking-wide-2 small-caps flex items-center justify-center gap-2 transition-colors",
            (draftEdgesJobId || draftEdges.isPending || dirty)
              ? "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed"
              : "bg-saffron text-paper hover:bg-saff-2",
          )}
          title={dirty ? "Save your changes first — drafting reads from disk" : undefined}
        >
          {draftEdges.isPending ? (
            <Loader2 size={13} className="animate-spin" strokeWidth={1.5} />
          ) : (
            <Sparkles size={14} strokeWidth={1.5} />
          )}
          Draft missing edges
        </button>
        <p className="mt-2 text-[10.5px] text-slate-2 leading-snug">
          Auto-routes edges between every entrance/parking/transit pair using the OSM footway graph.
          Adds them with TODO-stub instructions you'll refine in the inspector.
        </p>
        {draftEdges.isError && !draftEdgesJobId && (
          <p className="ff-mono text-[10.5px] text-rust mt-2">{(draftEdges.error as Error).message}</p>
        )}
        <JobInlineProgress
          jobId={draftEdgesJobId}
          onSettled={(status) => {
            if (status === "complete") {
              qc.invalidateQueries({ queryKey: queryKeys.facility(slug) });
            }
            // Clear after a beat so the user sees the green flash before the inline disappears
            setTimeout(() => setDraftEdgesJobId(null), 1200);
          }}
        />

        <button
          disabled={!!streetviewJobId || streetviewBulk.isPending || dirty}
          onClick={async () => {
            try {
              const res = await streetviewBulk.mutateAsync({ slug });
              setStreetviewJobId(res.job_id);
            } catch {
              // Inline error rendered below
            }
          }}
          className={cn(
            "mt-3 w-full h-10 rounded-sm text-[11.5px] tracking-wide-2 small-caps flex items-center justify-center gap-2 transition-colors",
            (streetviewJobId || streetviewBulk.isPending || dirty)
              ? "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed"
              : "bg-saffron text-paper hover:bg-saff-2",
          )}
          title={dirty ? "Save your changes first — drafting reads from disk" : undefined}
        >
          {streetviewBulk.isPending ? (
            <Loader2 size={13} className="animate-spin flex-shrink-0" strokeWidth={1.5} />
          ) : (
            <Sparkles size={14} className="flex-shrink-0" strokeWidth={1.5} />
          )}
          Draft from Street View
        </button>
        <p className="mt-2 text-[10.5px] text-slate-2 leading-snug">
          Drafts instructions for TODO-stub edges from Street View imagery.
          Review per-edge in the inspector.
        </p>
        {streetviewBulk.isError && !streetviewJobId && (
          <p className="ff-mono text-[10.5px] text-rust mt-2">{(streetviewBulk.error as Error).message}</p>
        )}
        <JobInlineProgress
          jobId={streetviewJobId}
          onSettled={(status) => {
            if (status === "complete") {
              qc.invalidateQueries({ queryKey: queryKeys.suggestions(slug) });
            }
            setTimeout(() => setStreetviewJobId(null), 1200);
          }}
        />

        {staleEdgeIndices.length > 0 && (
          <>
            <button
              disabled={dirty || reroute.isPending}
              onClick={() => reroute.mutate({ slug })}
              className={cn(
                "mt-3 w-full h-9 rounded-sm text-[11px] tracking-wide-2 small-caps flex items-center justify-center gap-2 transition-colors",
                dirty || reroute.isPending
                  ? "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed"
                  : "bg-ochre/15 text-ochre border border-ochre/40 hover:bg-ochre/25",
              )}
              title={dirty ? "Save your changes first — re-routing reads from disk" : undefined}
            >
              {reroute.isPending && <Loader2 size={12} className="animate-spin" strokeWidth={1.5} />}
              Re-route {staleEdgeIndices.length} stale edge{staleEdgeIndices.length === 1 ? "" : "s"}
            </button>
            <p className="mt-2 text-[10.5px] text-slate-2 leading-snug italic ff-display">
              Snaps the dragged endpoints back to the OSM footway graph. Needs the bootstrap
              <span className="ff-mono not-italic ml-1 text-ink">osm.json</span>.
            </p>
            {reroute.isError && (
              <p className="ff-mono text-[10.5px] text-rust mt-2 leading-snug">
                {(reroute.error as Error).message}
              </p>
            )}
            {reroute.isSuccess && reroute.data && (
              <p className="ff-mono text-[10.5px] text-moss mt-2 leading-snug">
                Re-routed {reroute.data.rerouted.length} edge{reroute.data.rerouted.length === 1 ? "" : "s"}
                {reroute.data.skipped.length > 0 && ` · ${reroute.data.skipped.length} skipped`}.
              </p>
            )}
          </>
        )}

        {/* Bulk-delete escape hatch — useful after a Draft Missing Edges run
            produces spaghetti and you want to start over. Typed-confirm
            because edge state is local-only until ⌘S, but unsaved drafts can
            still be hard to recover. */}
        <button
          disabled={draft.edges.length === 0}
          onClick={() => {
            const count = draft.edges.length;
            const answer = window.prompt(
              `Delete all ${count} edges? Nodes are kept.\n\nType "delete" to confirm. (Not yet saved — ⌘Z is not available.)`,
            );
            if (answer && answer.trim().toLowerCase() === "delete") {
              clearAllEdges();
            }
          }}
          className={cn(
            "mt-6 w-full h-9 rounded-sm text-[11px] tracking-wide-2 small-caps flex items-center justify-center gap-2 transition-colors",
            draft.edges.length === 0
              ? "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed"
              : "bg-rust/10 text-rust border border-rust/40 hover:bg-rust/20",
          )}
          title={draft.edges.length === 0 ? "No edges to delete" : `Delete all ${draft.edges.length} edges (keeps nodes)`}
        >
          <Trash2 size={12} strokeWidth={1.5} />
          Delete all {draft.edges.length} edge{draft.edges.length === 1 ? "" : "s"}
        </button>
        <p className="mt-2 text-[10.5px] text-slate-2 leading-snug italic ff-display">
          Wipes every edge but keeps the nodes. Useful after a noisy
          <span className="ff-mono not-italic mx-1 text-ink">Draft missing edges</span>
          run.
        </p>
          </>
        )}
      </aside>

      {/* Map */}
      <div className="flex-1 relative">
        <div className="absolute top-4 left-4 z-[400] flex items-center gap-2 px-3 h-8 bg-paper/90 border border-hairline rounded-sm backdrop-blur-sm crisp-shadow">
          <Link to="/" className="ff-mono text-[10px] tracking-wide-2 text-slate-2 hover:text-ink">ATLAS</Link>
          <ChevronRight size={11} className="text-slate-3" strokeWidth={1.5} />
          <span className="text-[12px]">{detail.facility.name}</span>
          <ChevronRight size={11} className="text-slate-3" strokeWidth={1.5} />
          <span className="ff-display italic text-[13px] text-saffron">Topology</span>
          {dirty && (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-saffron pulse-dot ml-2" />
              <span className="ff-mono text-[10px] tracking-wide-2 text-slate-2">unsaved</span>
            </>
          )}
        </div>

        <div className="absolute top-4 right-4 z-[400] flex items-center gap-2">
          <button
            onClick={frameAll}
            className="grid place-items-center w-8 h-8 bg-paper/90 border border-hairline rounded-sm backdrop-blur-sm crisp-shadow text-slate hover:text-ink hover:border-ink transition-colors"
            title="Frame all nodes"
          >
            <Maximize2 size={13} strokeWidth={1.5} />
          </button>
          <div className="flex flex-col items-center gap-1 px-3 py-2 bg-paper/90 border border-hairline rounded-sm backdrop-blur-sm crisp-shadow">
            <span className="ff-display italic text-[10px] text-saffron">N</span>
            <div className="w-px h-5 bg-ink" />
            <span className="ff-mono text-[8.5px] tracking-wide-2 text-slate-2">17z</span>
          </div>
        </div>

        <div
          ref={mapRef}
          className="absolute inset-0"
          data-tool={tool}
        />

        {lockedByOther && (
          <div className="absolute top-16 left-1/2 -translate-x-1/2 z-[400] flex items-center gap-2 px-3 h-8 bg-rust/95 text-paper rounded-sm crisp-shadow-strong">
            <span className="ff-mono text-[10px] tracking-wide-3 small-caps">
              {lockState?.held_by} is editing this facility — your saves will be rejected
            </span>
          </div>
        )}

        {mode === "draft" && proposal?.status === "needs_changes" && (
          <div className="absolute top-16 left-1/2 -translate-x-1/2 z-[400] flex items-center gap-2 px-3 h-8 bg-ochre/95 text-paper rounded-sm crisp-shadow-strong">
            <span className="ff-mono text-[10px] tracking-wide-3 small-caps">
              Needs changes{proposal.review_note ? ` — ${proposal.review_note}` : ""}
            </span>
          </div>
        )}

        {mode === "draft" && proposal?.status === "pending" && (
          <div className="absolute top-16 left-1/2 -translate-x-1/2 z-[400] flex items-center gap-2 px-3 h-8 bg-saffron/95 text-paper rounded-sm crisp-shadow-strong">
            <span className="ff-mono text-[10px] tracking-wide-3 small-caps">
              Submitted for review · awaiting admin
            </span>
          </div>
        )}

        {mode === "draft" && !proposal && (
          <div className="absolute top-16 left-1/2 -translate-x-1/2 z-[400] flex items-center gap-2 px-3 h-8 bg-paper/95 border border-hairline rounded-sm crisp-shadow">
            <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-slate">
              Personal draft — submit for review when ready
            </span>
          </div>
        )}

        {!lockedByOther && tool !== "select" && (
          <div className="absolute top-16 left-1/2 -translate-x-1/2 z-[400] flex items-center gap-2 px-3 h-8 bg-saffron/95 text-paper rounded-sm crisp-shadow-strong pointer-events-none">
            <span className="ff-mono text-[10px] tracking-wide-3 small-caps">
              {tool === "addNode"
                ? "Click empty map to drop a node · right-click a node to delete"
                : edgeStartId
                  ? `Click another node to finish · click empty map to bend the path${waypointVersion > 0 && waypointsRef.current.length > 0 ? " · Backspace undo" : ""}`
                  : "Click a node to start an edge"}
            </span>
            <span className="text-paper/70 text-[10px] ff-mono">· Esc</span>
          </div>
        )}

        {flash && (
          <div className="absolute top-28 left-1/2 -translate-x-1/2 z-[400] flex items-center gap-2 px-3 h-8 bg-ochre/95 text-paper rounded-sm crisp-shadow-strong pointer-events-none">
            <span className="ff-mono text-[10px] tracking-wide-3 small-caps">{flash}</span>
          </div>
        )}

        <div className="absolute bottom-5 left-1/2 -translate-x-1/2 z-[400] flex items-center gap-1 px-2 py-1.5 bg-paper border border-hairline rounded-sm crisp-shadow-strong">
          <CmdKey label="Select" k="V" active={tool === "select"}  onClick={() => setTool("select")} />
          <CmdKey label="Node"   k="N" active={tool === "addNode"} onClick={() => setTool("addNode")} />
          <CmdKey label="Edge"   k="E" active={tool === "addEdge"} onClick={() => setTool("addEdge")} />
          <span className="h-5 w-px bg-hairline mx-1.5" />
          <CmdBarButton
            label={validateLabel(dryRun.data)}
            tone={validateTone(dryRun.data)}
            onClick={() => { qc.invalidateQueries({ queryKey: ["publish-dry-run", slug] }); setPublishOpen(true); }}
          />
          <CmdBarButton label="Preview" onClick={() => navigate({ to: "/preview", search: { slug } })} />
          <CmdKey label="Publish" k={"\u2318\u23ce"} primary onClick={() => setPublishOpen(true)} />
          <span className="h-5 w-px bg-hairline mx-1.5" />
          <CmdKey
            label="Palette"
            k={"\u2318K"}
            onClick={() => window.dispatchEvent(new Event(PALETTE_EVENT.togglePalette))}
          />
        </div>
      </div>
      <PublishModal
        open={publishOpen}
        onClose={() => setPublishOpen(false)}
        slug={slug}
        facilityName={detail.facility.name}
      />
      {sel && (
        <DepartmentPickerModal
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
          node={sel}
          departments={deptController.drafts}
          onMap={(deptNames, nodeId) => {
            // Picker submit is a commit-intent action — apply + save in one go.
            deptController.mapAndSave(deptNames, nodeId);
          }}
        />
      )}
      {/* Inspector */}
      <aside className="w-[360px] border-l border-hairline bg-paper overflow-y-auto flex flex-col">
        <div className="flex items-center border-b border-hairline px-2 sticky top-0 bg-paper z-10">
          <button
            onClick={() => setInspectorTab("node")}
            className={cn(
              "px-3 h-9 text-[10.5px] tracking-wide-2 small-caps transition-colors",
              inspectorTab === "node"
                ? "text-ink border-b-2 border-saffron -mb-px"
                : "text-slate-2 hover:text-ink",
            )}
          >
            Node {sel ? `· ${sel.label}` : ""}
          </button>
          <button
            onClick={() => setInspectorTab("departments")}
            className={cn(
              "px-3 h-9 text-[10.5px] tracking-wide-2 small-caps transition-colors flex items-center gap-1.5",
              inspectorTab === "departments"
                ? "text-ink border-b-2 border-saffron -mb-px"
                : "text-slate-2 hover:text-ink",
            )}
          >
            Departments
            <span className="ff-mono text-[10px] text-slate-2">
              {(detail.facility.departments as unknown[] | undefined)?.length ?? 0}
            </span>
          </button>
          <button
            onClick={() => setInspectorTab("facility")}
            className={cn(
              "px-3 h-9 text-[10.5px] tracking-wide-2 small-caps transition-colors",
              inspectorTab === "facility"
                ? "text-ink border-b-2 border-saffron -mb-px"
                : "text-slate-2 hover:text-ink",
            )}
          >
            Facility
          </button>
        </div>

        {inspectorTab === "facility" && (
          <FacilityPanel
            key={slug}
            slug={slug}
            facility={detail.facility as Record<string, unknown>}
          />
        )}

        {inspectorTab === "departments" && (
          <DepartmentsPanel
            key={slug}
            slug={slug}
            facilityName={detail.facility.name}
            nodes={draft.nodes}
            controller={deptController}
            assigningNames={assigningNames}
            setAssigningNames={setAssigningNames}
            pendingAssignNodeId={pendingAssignNodeId}
            consumePendingAssignment={() => setPendingAssignNodeId(null)}
          />
        )}

        {inspectorTab === "node" && selectedEdge && (
          <EdgeInspector
            edge={selectedEdge.edge}
            edgeIdx={selectedEdge.idx}
            nodes={draft.nodes}
            slug={slug}
            suggestions={suggestionsQuery.data?.suggestions ?? []}
            onInstructionChange={updateEdgeInstruction}
            onFeaturesChange={updateEdgeFeatures}
            onDelete={deleteEdgeAt}
            onClose={() => setSelectedEdgeKey(null)}
          />
        )}

        {inspectorTab === "node" && !selectedEdge && sel && (
          <div key={sel.id} className="px-5 py-5 rise">
            <PanelHeader num="04" title="Inspector" right={TYPE_LABEL[sel.type]} />

            <div className="flex items-start gap-3 mb-4">
              <div
                className="grid place-items-center w-9 h-9 rounded-sm border border-hairline bg-paper-2"
                style={{ color: TYPE_COLOR[sel.type] }}
              >
                <span className="block w-2.5 h-2.5 rounded-full" style={{ background: TYPE_COLOR[sel.type] }} />
              </div>
              <div className="flex-1">
                <h2 className="ff-display text-[22px] leading-tight">{sel.label}</h2>
                <code className="ff-mono text-[10.5px] text-slate">{sel.id}</code>
              </div>
            </div>

            <Field label="Visible cue · description">
              <textarea
                className="w-full bg-paper-2 border border-hairline rounded-sm p-2.5 text-[12.5px] leading-relaxed resize-none ff-display"
                rows={3}
                value={sel.description}
                onChange={(e) => updateNode(sel.id, { description: e.target.value })}
              />
              <p className="mt-1.5 text-[10.5px] text-slate-2 leading-snug italic">
                What does the patient see standing here? Specific landmarks, awnings, signage. The model
                surfaces this when re-orienting.
              </p>
            </Field>

            <Section
              kind="node" subjectId={sel.id} name="advanced"
              title="Advanced — phrasings"
              count={sel.keywords.length}
              defaultOpen={false}
            >
              <p className="text-[11.5px] text-slate-2 italic ff-display leading-snug mb-2">
                Patient phrasings — what someone might say if they were lost.
                Auto-generated by the <span className="ff-mono not-italic text-ink">Expand aliases</span> job;
                hand-edit only when the model misses a common phrasing.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {sel.keywords.map((k, i) => (
                  <span
                    key={i}
                    className="ff-mono text-[10.5px] tracking-wide-2 px-2 py-0.5 bg-paper-2 border border-hairline rounded-sm flex items-center gap-1.5"
                  >
                    {k}
                    <button
                      className="text-slate-3 hover:text-rust"
                      onClick={() =>
                        updateNode(sel.id, { keywords: sel.keywords.filter((_, ii) => ii !== i) })
                      }
                    >
                      ×
                    </button>
                  </span>
                ))}
                <input
                  value={keywordDraft}
                  onChange={(e) => setKeywordDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== "Enter" && e.key !== ",") return;
                    e.preventDefault();
                    const trimmed = keywordDraft.trim().replace(/,$/, "").trim();
                    if (!trimmed) return;
                    if (sel.keywords.includes(trimmed)) {
                      setKeywordDraft("");
                      return;
                    }
                    updateNode(sel.id, { keywords: [...sel.keywords, trimmed] });
                    setKeywordDraft("");
                  }}
                  placeholder="add keyword + Enter"
                  className="ff-mono text-[10.5px] tracking-wide-2 px-2 h-[22px] border border-dashed border-hairline rounded-sm text-ink placeholder:text-slate-3 bg-transparent focus:border-saffron outline-none w-[150px]"
                />
              </div>
            </Section>

            <Field label="Coordinates · lat, lng">
              <div className="grid grid-cols-2 gap-2">
                <input
                  className="bg-paper-2 border border-hairline rounded-sm px-2.5 h-8 text-[12px] ff-mono"
                  value={sel.lat.toFixed(6)}
                  onChange={(e) => {
                    const v = parseFloat(e.target.value);
                    if (!Number.isNaN(v)) updateNode(sel.id, { lat: v });
                  }}
                />
                <input
                  className="bg-paper-2 border border-hairline rounded-sm px-2.5 h-8 text-[12px] ff-mono"
                  value={sel.lng.toFixed(6)}
                  onChange={(e) => {
                    const v = parseFloat(e.target.value);
                    if (!Number.isNaN(v)) updateNode(sel.id, { lng: v });
                  }}
                />
              </div>
            </Field>

            <Section
              kind="node"
              subjectId={sel.id}
              name="photos"
              title="Photos"
              defaultOpen={false}
            >
              <PhotoUploadPanel subject={{ kind: "node", slug, nodeId: sel.id }} />
            </Section>

            <Field label={`Connected edges (${incidentEdges.length})`}>
              <div className="space-y-1">
                {incidentEdges.map((e) => {
                  const otherId = e.from === sel.id ? e.to : e.from;
                  const otherLabel = draft.nodes.find((n) => n.id === otherId)?.label ?? otherId;
                  const direction = e.from === sel.id ? "→" : "←";
                  const isEmpty = !e.instruction;
                  const suggestion = (suggestionsQuery.data?.suggestions ?? []).find(
                    (s) => s.from === e.from && s.to === e.to,
                  );
                  return (
                    <button
                      key={`${e.from}__${e.to}`}
                      onClick={() => setSelectedEdgeKey(`${e.from}__${e.to}`)}
                      className="w-full flex items-center gap-2 px-2.5 h-8 rounded-sm border border-hairline bg-paper hover:bg-paper-2 hover:border-saffron/50 transition-colors text-left group"
                    >
                      <span className="text-saffron ff-mono text-[12px]">{direction}</span>
                      <span className="text-[12px] text-ink truncate flex-1">{otherLabel}</span>
                      {isEmpty && (
                        <span className="ff-mono text-[9.5px] tracking-wide-2 small-caps text-ochre">
                          todo
                        </span>
                      )}
                      {suggestion && (
                        <Sparkles size={10} className="text-saffron flex-shrink-0" strokeWidth={1.5} />
                      )}
                      <ArrowRight size={10} className="text-slate-2 group-hover:text-saffron flex-shrink-0" strokeWidth={1.5} />
                    </button>
                  );
                })}
                {incidentEdges.length === 0 && (
                  <p className="ff-mono text-[10.5px] text-slate-2 italic">No edges incident to this node.</p>
                )}
              </div>
              <p className="ff-mono text-[10.5px] text-slate-2 italic mt-2 leading-snug">
                Click an edge to open it in the inspector — instruction, photos,
                and drafts edit there.
              </p>
            </Field>

            <Field label={`Departments routing through here (${departments.length})`}>
              {departments.length > 0 ? (
                <div className="space-y-1">
                  {departments.slice(0, 5).map((d, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 px-2 py-1.5 hover:bg-paper-2 rounded-sm group"
                    >
                      <span className="text-[12px] flex-1 truncate">{d.name}</span>
                      <span className="ff-mono text-[10px] text-slate-2">
                        {d.floor ?? "—"}
                      </span>
                      <button
                        onClick={() => deptController.unmapAndSave(d.name)}
                        title={`Unmap "${d.name}" from this node`}
                        aria-label={`Unmap ${d.name}`}
                        className="text-slate-3 hover:text-rust opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <Trash2 size={11} strokeWidth={1.5} />
                      </button>
                    </div>
                  ))}
                  {departments.length > 5 && (
                    <button
                      onClick={() => setInspectorTab("departments")}
                      className="mt-2 text-[10.5px] tracking-wide-2 small-caps text-slate hover:text-ink flex items-center gap-1.5"
                    >
                      <ArrowRight size={11} strokeWidth={1.5} /> Show all {departments.length} in Departments tab
                    </button>
                  )}
                </div>
              ) : (
                <p className="ff-mono text-[10.5px] text-slate-2 italic">
                  No department pins this node yet.
                </p>
              )}
              {mode === "shared" && (
                <button
                  onClick={() => setPickerOpen(true)}
                  className="mt-2 w-full flex items-center justify-center gap-1.5 px-3 h-8 rounded-sm border border-dashed border-hairline text-[11px] tracking-wide-2 small-caps text-slate hover:text-saffron hover:border-saffron transition-colors"
                >
                  <Plus size={11} strokeWidth={1.5} /> Map departments to this node
                </button>
              )}
              {deptController.save.isPending && (
                <p className="ff-mono text-[10.5px] text-saffron italic mt-2 leading-snug flex items-center gap-1.5">
                  <Loader2 size={10} className="animate-spin" strokeWidth={1.5} /> Saving department mapping…
                </p>
              )}
              {deptController.dirty && !deptController.save.isPending && (
                <p className="ff-mono text-[10.5px] text-ochre italic mt-2 leading-snug">
                  Unsaved department edits exist — visit the Departments tab to save.
                </p>
              )}
            </Field>

            <div className="pt-4 border-t border-hairline mt-2 flex items-center gap-2">
              <button
                disabled={!dirty || saveMutation.isPending}
                onClick={() => saveMutation.mutate({ slug, topology: draft })}
                className={cn(
                  "flex-1 h-9 rounded-sm text-[11px] tracking-wide-2 small-caps transition-colors flex items-center justify-center gap-2",
                  dirty
                    ? "bg-ink text-paper hover:bg-ink-2"
                    : "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed",
                )}
              >
                {saveMutation.isPending && <Loader2 size={13} className="animate-spin" strokeWidth={1.5} />}
                {saveMutation.isPending
                  ? "Saving…"
                  : dirty
                    ? "Save changes"
                    : saveMutation.isSuccess ? "Saved" : "No changes"}
              </button>
              <button
                onClick={() => navigate({ to: "/preview", search: { slug } })}
                className="px-3 h-9 border border-hairline rounded-sm text-[11px] tracking-wide-2 small-caps text-slate hover:text-ink"
                title="Open the patient preview for this facility"
              >
                Preview
              </button>
            </div>
            {saveMutation.isError && (
              <p className="ff-mono text-[10.5px] text-rust mt-2">
                Save failed: {(saveMutation.error as Error).message}
              </p>
            )}

            <div className="pt-3 mt-3 border-t border-hairline">
              <button
                onClick={() => {
                  if (confirm(`Delete node "${sel.label}"? This also removes ${incidentEdges.length} incident edge${incidentEdges.length === 1 ? "" : "s"}.`)) {
                    deleteNode(sel.id);
                  }
                }}
                className="text-[10.5px] tracking-wide-2 small-caps text-slate-2 hover:text-rust flex items-center gap-1.5"
              >
                <Trash2 size={11} strokeWidth={1.5} /> Delete this node
              </button>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

// ----------- helpers -----------

function computeCenter(nodes: TopologyNode[]): [number, number] {
  if (!nodes.length) return [42.36, -71.06]; // Boston-ish default
  const lat = nodes.reduce((s, n) => s + n.lat, 0) / nodes.length;
  const lng = nodes.reduce((s, n) => s + n.lng, 0) / nodes.length;
  return [lat, lng];
}

function PanelHeader({ num, title, right }: { num: string; title: string; right?: string }) {
  return (
    <div className="flex items-baseline gap-2 mb-3">
      <span className="ff-mono text-[9.5px] tracking-wide-3 small-caps text-saffron">{num} / {title}</span>
      <span className="flex-1 h-px bg-hairline" />
      {right && <span className="ff-mono text-[10px] text-slate-2">{right}</span>}
    </div>
  );
}

function LayerRow({ label, on, toggle, swatch }: { label: string; on: boolean; toggle: () => void; swatch: string }) {
  return (
    <button
      onClick={toggle}
      className="w-full flex items-center gap-2.5 py-1.5 px-2 -mx-2 rounded-sm hover:bg-paper-2 transition-colors text-left"
    >
      <span
        className="w-3.5 h-3.5 rounded-sm border-[1.5px] grid place-items-center"
        style={{ borderColor: on ? swatch : "#D9D2C2", background: on ? swatch : "transparent" }}
      >
        {on && <Check size={9} strokeWidth={3} className="text-paper" />}
      </span>
      <span className="text-[11.5px]">{label}</span>
    </button>
  );
}

const HEALTH_TONE = { moss: "text-moss", ochre: "text-ochre", rust: "text-rust", ink: "text-ink" } as const;

function HealthRow({ label, value, tone }: { label: string; value: string; tone: keyof typeof HEALTH_TONE }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate">{label}</span>
      <span className={cn("ff-mono", HEALTH_TONE[tone])}>{value}</span>
    </div>
  );
}

function CmdBarButton({ label, tone, onClick }: { label: string; tone?: "moss" | "ochre"; onClick?: () => void }) {
  const toneClass = tone === "moss" ? "text-moss" : tone === "ochre" ? "text-ochre" : "text-slate hover:text-ink";
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-2.5 h-7 rounded-sm text-[11px] tracking-wide-2 small-caps transition-colors hover:bg-paper-2",
        toneClass,
      )}
    >
      {label}
    </button>
  );
}

interface CmdKeyProps {
  label: string;
  k: string;
  primary?: boolean;
  active?: boolean;
  tone?: "moss" | "ochre";
  onClick?: () => void;
}

function CmdKey({ label, k, primary, active, tone, onClick }: CmdKeyProps) {
  const toneClasses =
    tone === "moss" ? "text-moss" : tone === "ochre" ? "text-ochre" : null;
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 px-2.5 h-7 rounded-sm text-[11px] transition-colors",
        primary
          ? "bg-saffron text-paper hover:bg-saff-2"
          : active
            ? "bg-ink text-paper"
            : toneClasses
              ? `${toneClasses} hover:bg-paper-2`
              : "text-slate hover:text-ink hover:bg-paper-2",
      )}
    >
      <span className="tracking-wide-2 small-caps">{label}</span>
      <kbd
        className={cn(
          "ff-mono text-[9.5px] tracking-wide-2 px-1 py-0.5 rounded-sm border",
          primary
            ? "border-paper/40 text-paper/85"
            : active
              ? "border-paper/30 text-paper/85"
              : "border-hairline text-slate-2",
        )}
      >
        {k}
      </kbd>
    </button>
  );
}


function Loading({ message }: { message: string }) {
  return (
    <div className="h-full grid place-items-center">
      <div className="text-center">
        <Loader2 size={28} className="text-saffron animate-spin mx-auto mb-3" strokeWidth={1.5} />
        <p className="ff-mono text-[11px] tracking-wide-2 small-caps text-slate-2">{message}</p>
      </div>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="h-full grid place-items-center">
      <div className="max-w-md text-center px-6">
        <p className="ff-mono text-[10px] tracking-wide-3 small-caps text-rust mb-2">Failed to load</p>
        <p className="ff-display text-[18px] mb-3">{message}</p>
        <Link to="/" className="ff-mono text-[11px] tracking-wide-2 small-caps text-saffron hover:text-saff-2">
          ← back to facilities
        </Link>
      </div>
    </div>
  );
}

function NoTopologyState({ slug, facilityName }: { slug: string; facilityName: string }) {
  return (
    <div className="h-full grid place-items-center">
      <div className="max-w-md text-center px-6">
        <p className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron mb-2">{slug}</p>
        <p className="ff-display text-[24px] mb-3 leading-tight">
          {facilityName} has no topology yet.
        </p>
        <p className="text-[13px] text-slate mb-5 leading-relaxed">
          Locate the facility on OSM to seed nodes, or import an existing <span className="ff-mono">topology.json</span>.
        </p>
        <Link to="/" className="ff-mono text-[11px] tracking-wide-2 small-caps text-saffron hover:text-saff-2">
          ← back to facilities
        </Link>
      </div>
    </div>
  );
}
