import { useState } from "react";
import { Trash2 } from "lucide-react";
import { PhotoUploadPanel } from "@/components/PhotoUploadPanel";
import { DraftsSection } from "./DraftsSection";
import { PhotoMiniMap } from "./PhotoMiniMap";
import { Section } from "./Section";
import { useEdgePhotos } from "@/lib/api";
import type { TopologyEdge, TopologyNode, AccessibilityFeature } from "@/lib/types";
import type { Suggestion } from "@/lib/api";

interface Props {
  edge: TopologyEdge;
  edgeIdx: number;
  nodes: TopologyNode[];
  slug: string;
  /** Suggestion sidecar entries indexed by `from -> to`. Optional in shared mode only. */
  suggestions: Suggestion[];
  onInstructionChange: (idx: number, instr: string) => void;
  onFeaturesChange: (idx: number, features: AccessibilityFeature[]) => void;
  onDelete: (idx: number) => void;
  onClose: () => void;
}

const ACCESSIBILITY: { key: AccessibilityFeature; label: string }[] = [
  { key: "elevator", label: "Elevator" },
  { key: "ramp", label: "Ramp" },
  { key: "automatic_doors", label: "Auto doors" },
  { key: "accessible_entrance", label: "Accessible entrance" },
  { key: "stairs", label: "Stairs" },
];

/**
 * Right-panel inspector when an edge is selected. Mirrors the node inspector
 * but scoped to an edge: instruction prose, accessibility, photo uploads,
 * draft suggestions (Phase 3), geometry summary, danger zone.
 *
 * Drafts (both Street View and user-photo sources) live inline as cards in
 * the Drafts section — the prior modal flow was retired in docs/30.
 */
export function EdgeInspector({
  edge, edgeIdx, nodes, slug, suggestions,
  onInstructionChange, onFeaturesChange, onDelete, onClose,
}: Props) {
  const fromNode = nodes.find((n) => n.id === edge.from);
  const toNode = nodes.find((n) => n.id === edge.to);
  const fromLabel = fromNode?.label ?? edge.from;
  const toLabel = toNode?.label ?? edge.to;
  const subjectId = `${edge.from}__${edge.to}`;

  const [instructionDraft, setInstructionDraft] = useState(edge.instruction ?? "");
  // Keep local state in sync if the edge changes underneath (e.g. accept).
  const lastEdgeKey = `${edge.from}__${edge.to}::${edge.instruction ?? ""}`;
  const [lastSeen, setLastSeen] = useState(lastEdgeKey);
  if (lastSeen !== lastEdgeKey) {
    setLastSeen(lastEdgeKey);
    setInstructionDraft(edge.instruction ?? "");
  }

  const features = edge.accessibility_features ?? [];
  const toggleFeature = (feat: AccessibilityFeature) => {
    const next = features.includes(feat)
      ? features.filter((f) => f !== feat)
      : [...features, feat];
    onFeaturesChange(edgeIdx, next);
  };

  const edgeSuggestions = suggestions.filter(
    (s) => s.from === edge.from && s.to === edge.to,
  );

  // GPS-redraw flag: opt-in toggle for replacing geometry from a photo polyline
  // when approving a user_photos draft. Defaults to ON when there are
  // GPS-bearing photos (otherwise it has no effect).
  const photosQuery = useEdgePhotos(slug, edge.from, edge.to);
  const gpsCount = (photosQuery.data?.photos ?? []).filter(
    (p) => p.lat != null && p.lng != null,
  ).length;
  const [replaceGeometry, setReplaceGeometry] = useState(true);

  const distance = edge.distance_meters
    ? `${Math.round(edge.distance_meters)} m`
    : "—";
  const geometryKind = edge.geometry?.length
    ? edge.stale_geometry ? "routed (stale)" : `routed · ${edge.geometry.length} points`
    : "straight line";

  return (
    <div className="flex flex-col min-h-0 flex-1">
      <header className="px-5 py-4 border-b border-hairline">
        <div className="flex items-baseline gap-2">
          <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron">
            Edge / walking segment
          </span>
          <button
            onClick={onClose}
            className="ml-auto ff-mono text-[10px] tracking-wide-2 small-caps text-slate hover:text-ink"
          >
            Close
          </button>
        </div>
        <h2 className="ff-display italic text-[20px] leading-tight mt-1">
          {fromLabel} <span className="text-saffron">→</span> {toLabel}
        </h2>
        <p className="ff-mono text-[10.5px] text-slate-2 mt-1">
          {edge.from} → {edge.to} · {distance}
        </p>
      </header>

      <div className="px-5 overflow-y-auto flex-1">
        <Section
          kind="edge" subjectId={subjectId} name="instruction"
          title="Instruction" defaultOpen
        >
          <textarea
            value={instructionDraft}
            onChange={(e) => setInstructionDraft(e.target.value)}
            onBlur={() => {
              if (instructionDraft !== (edge.instruction ?? "")) {
                onInstructionChange(edgeIdx, instructionDraft);
              }
            }}
            placeholder='Walk past the lobby and through the doors marked "MEDICAL OFFICES 3".'
            className="w-full bg-paper-2 border border-hairline rounded-sm px-3 py-2 text-[13px] leading-relaxed outline-none focus:border-saffron min-h-[88px] resize-y"
          />
          <p className="ff-mono text-[10.5px] text-slate-2 italic mt-1.5 leading-snug">
            Patient-facing prose. 1–2 sentences, visual landmarks, no compass directions.
          </p>
        </Section>

        <Section
          kind="edge" subjectId={subjectId} name="accessibility"
          title="Accessibility"
          count={`${features.length} of ${ACCESSIBILITY.length}`}
        >
          <div className="grid grid-cols-2 gap-2">
            {ACCESSIBILITY.map(({ key, label }) => (
              <label key={key} className="flex items-center gap-2 text-[12px] cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={features.includes(key)}
                  onChange={() => toggleFeature(key)}
                  className="accent-saffron"
                />
                <span className="text-ink-2">{label}</span>
              </label>
            ))}
          </div>
        </Section>

        <Section
          kind="edge" subjectId={subjectId} name="photos"
          title="Photos"
          defaultOpen
        >
          {(photosQuery.data?.photos ?? []).length > 0 && (
            <div className="mb-3">
              <PhotoMiniMap photos={photosQuery.data?.photos ?? []} />
            </div>
          )}
          <PhotoUploadPanel
            subject={{ kind: "edge", slug, fromId: edge.from, toId: edge.to }}
          />
        </Section>

        <Section
          kind="edge" subjectId={subjectId} name="drafts"
          title="Drafts"
          count={edgeSuggestions.length > 0 ? `${edgeSuggestions.length} ready` : "—"}
          defaultOpen
        >
          {gpsCount >= 2 && (
            <label className="flex items-center gap-2 text-[11.5px] mb-3 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={replaceGeometry}
                onChange={(e) => setReplaceGeometry(e.target.checked)}
                className="accent-saffron"
              />
              <span className="text-ink-2">
                Redraw edge geometry from GPS on approve
                <span className="block ff-mono text-[10px] text-slate-2 italic mt-0.5">
                  Replaces the current path with the polyline through {gpsCount} GPS points.
                </span>
              </span>
            </label>
          )}
          <DraftsSection
            slug={slug}
            fromId={edge.from}
            toId={edge.to}
            suggestions={edgeSuggestions}
            replaceGeometry={replaceGeometry}
          />
        </Section>

        <Section
          kind="edge" subjectId={subjectId} name="geometry"
          title="Geometry"
          count={geometryKind}
        >
          <p className="ff-mono text-[11px] text-slate-2 leading-snug">
            {edge.geometry?.length
              ? `Polyline with ${edge.geometry.length} vertices.`
              : "Straight line between endpoints."}
            {edge.stale_geometry && (
              <span className="block mt-1 text-ochre">
                Stale: an endpoint moved. Re-run the Reroute edges job to refresh.
              </span>
            )}
          </p>
        </Section>

        <Section
          kind="edge" subjectId={subjectId} name="danger"
          title="Danger zone"
        >
          <button
            onClick={() => {
              if (confirm(`Delete edge ${fromLabel} → ${toLabel}?`)) {
                onDelete(edgeIdx);
                onClose();
              }
            }}
            className="flex items-center gap-2 px-3 h-8 rounded-sm border border-rust/50 text-rust text-[11px] tracking-wide-2 small-caps hover:bg-rust/8"
          >
            <Trash2 size={11} strokeWidth={1.5} />
            Delete edge
          </button>
        </Section>
      </div>
    </div>
  );
}
