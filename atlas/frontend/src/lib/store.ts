import { create } from "zustand";
import type { FacilityMeta } from "./types";

/**
 * UI-only state. Server state lives in TanStack Query.
 *
 * Anything that needs to survive a page reload should round-trip via the URL
 * (TanStack Router params/search) or the backend, not Zustand.
 */
interface AtlasState {
  activeFacility: FacilityMeta | null;
  setActiveFacility: (f: FacilityMeta | null) => void;

  selectedNodeId: string | null;
  setSelectedNodeId: (id: string | null) => void;

  // Edge selection key is `${from}__${to}`. Mutually exclusive with node
  // selection — selecting one clears the other so the right inspector has a
  // single subject to render.
  selectedEdgeKey: string | null;
  setSelectedEdgeKey: (key: string | null) => void;

  // Open/closed state for collapsible inspector sections, keyed by
  // `${kind}:${id}:${sectionName}`. Persists across inspector switches so the
  // editor doesn't have to re-open Photos every time they jump between nodes.
  inspectorSections: Record<string, boolean>;
  setInspectorSection: (key: string, open: boolean) => void;

  editorTool: "select" | "addNode" | "addEdge";
  setEditorTool: (tool: AtlasState["editorTool"]) => void;

  layers: {
    osmFootprints: boolean;
    topology: boolean;
    departments: boolean;
    footways: boolean;
    satellite: boolean;
  };
  toggleLayer: (key: keyof AtlasState["layers"]) => void;

  // Settings → Test connection results, keyed by card id (e.g. "dept-extract").
  // Survives unmount of SettingsView so navigating away and back keeps the
  // last result on screen instead of reverting to "Not tested".
  connectionTests: Record<string, ConnectionTestRecord | undefined>;
  setConnectionTest: (key: string, record: ConnectionTestRecord) => void;
}

export interface ConnectionTestRecord {
  ok: boolean;
  latencyMs?: number;
  error?: string;
  sample?: string;
  testedAt: number;
}

export const useAtlasStore = create<AtlasState>((set) => ({
  activeFacility: null,
  setActiveFacility: (f) => set({ activeFacility: f }),

  selectedNodeId: "mob5_entrance",
  setSelectedNodeId: (id) => set({ selectedNodeId: id, selectedEdgeKey: null }),

  selectedEdgeKey: null,
  setSelectedEdgeKey: (key) => set({ selectedEdgeKey: key, selectedNodeId: null }),

  inspectorSections: {},
  setInspectorSection: (key, open) =>
    set((state) => ({ inspectorSections: { ...state.inspectorSections, [key]: open } })),

  editorTool: "select",
  setEditorTool: (tool) => set({ editorTool: tool }),

  layers: {
    osmFootprints: true,
    topology: true,
    departments: false,
    footways: false,
    satellite: false,
  },
  toggleLayer: (key) =>
    set((state) => ({ layers: { ...state.layers, [key]: !state.layers[key] } })),

  connectionTests: {},
  setConnectionTest: (key, record) =>
    set((state) => ({ connectionTests: { ...state.connectionTests, [key]: record } })),
}));
