import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ChevronDown, ChevronRight, Loader2, Plus, Search, Sparkles, Target, Trash2 } from "lucide-react";
import type { Department } from "@/lib/api";
import { queryKeys, useExpandAliases } from "@/lib/api";
import { useJobStream } from "@/lib/jobs";
import type { TopologyNode } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ExtractDepartmentsModal } from "./ExtractDepartmentsModal";
import type { useDepartmentEditor } from "./useDepartmentEditor";

type Filter = "all" | "mapped" | "unmapped" | "stale";

interface Props {
  slug: string;
  facilityName: string;
  nodes: TopologyNode[];
  /** Lifted controller — see useDepartmentEditor. */
  controller: ReturnType<typeof useDepartmentEditor>;
  /** When non-null, the next node click maps these dept names to that node. */
  assigningNames: string[] | null;
  setAssigningNames: (names: string[] | null) => void;
  /** Bumps when an outside event (a node click) just arrived. */
  pendingAssignNodeId: string | null;
  consumePendingAssignment: () => void;
}

export function DepartmentsPanel({
  slug, facilityName, nodes, controller,
  assigningNames, setAssigningNames,
  pendingAssignNodeId, consumePendingAssignment,
}: Props) {
  const { drafts, setDrafts, save, dirty, duplicateNames, mapAndSave } = controller;

  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const nodeIds = useMemo(() => new Set(nodes.map((n) => n.id)), [nodes]);

  // Extract-from-URL modal + Expand-aliases job state.
  const [extractOpen, setExtractOpen] = useState(false);
  const expandAliases = useExpandAliases();
  const [aliasJobId, setAliasJobId] = useState<string | null>(null);
  const aliasJob = useJobStream(aliasJobId);
  const qc = useQueryClient();
  useEffect(() => {
    if (aliasJob.status === "complete") {
      qc.invalidateQueries({ queryKey: queryKeys.facility(slug) });
    }
  }, [aliasJob.status, slug, qc]);

  const aliasInflight = !!aliasJobId && aliasJob.status !== "complete" && aliasJob.status !== "failed";
  const expandedTotal = drafts.reduce((s, d) => s + (d.aliases?.length ?? 0), 0);

  // ⌘S support.
  useEffect(() => {
    const onSave = () => {
      if (!dirty || save.isPending || duplicateNames.size > 0) return;
      save.mutate({ slug, departments: drafts });
    };
    window.addEventListener("atlas:save-current-tab", onSave);
    return () => window.removeEventListener("atlas:save-current-tab", onSave);
  }, [dirty, save, slug, drafts, duplicateNames.size]);

  // Pending node click → apply to all assigningNames at once AND persist.
  // The Assign-then-click-map gesture is a commit-intent action; auto-save
  // matches the picker's behavior so the editor doesn't have to context-switch
  // to the dept tab and click Save after every mapping.
  useEffect(() => {
    if (!pendingAssignNodeId || !assigningNames || assigningNames.length === 0) return;
    mapAndSave(assigningNames, pendingAssignNodeId);
    setAssigningNames(null);
    consumePendingAssignment();
  }, [pendingAssignNodeId, assigningNames, mapAndSave, setAssigningNames, consumePendingAssignment]);

  const counts = useMemo(() => {
    const mapped = drafts.filter((d) => d.topology_node_id).length;
    const stale  = drafts.filter((d) => d.topology_node_id && !nodeIds.has(d.topology_node_id)).length;
    return { all: drafts.length, mapped, unmapped: drafts.length - mapped, stale };
  }, [drafts, nodeIds]);

  const filtered = drafts.filter((d) => {
    const matchesText =
      !search ||
      d.name.toLowerCase().includes(search.toLowerCase()) ||
      (d.building?.toLowerCase().includes(search.toLowerCase()) ?? false);
    if (!matchesText) return false;
    const isMapped = !!d.topology_node_id;
    const isStale  = isMapped && !nodeIds.has(d.topology_node_id!);
    if (filter === "mapped")    return isMapped;
    if (filter === "unmapped")  return !isMapped;
    if (filter === "stale")     return isStale;
    return true;
  });

  // Group unmapped departments by building+floor for the bulk-map action.
  // Only a group with ≥2 unmapped depts is worth a bulk affordance — singles
  // are already a one-step assign in their own row.
  const bulkGroups = useMemo(() => {
    const groups = new Map<string, { key: string; building: string; floor: string; depts: Department[] }>();
    for (const d of drafts) {
      if (d.topology_node_id) continue;
      const building = d.building?.trim() ?? "";
      const floor = d.floor?.trim() ?? "";
      if (!building && !floor) continue;
      const key = `${building}::${floor}`;
      if (!groups.has(key)) groups.set(key, { key, building, floor, depts: [] });
      groups.get(key)!.depts.push(d);
    }
    return [...groups.values()].filter((g) => g.depts.length >= 2);
  }, [drafts]);

  const updateDeptAt = (idx: number, patch: Partial<Department>) => {
    setDrafts((arr) => arr.map((d, i) => (i === idx ? { ...d, ...patch } : d)));
  };
  const removeDeptAt = (idx: number) => {
    setDrafts((arr) => arr.filter((_, i) => i !== idx));
    if (expandedIdx === idx) setExpandedIdx(null);
    else if (expandedIdx !== null && idx < expandedIdx) setExpandedIdx(expandedIdx - 1);
  };

  const isAssigningSingle = (name: string) =>
    assigningNames !== null && assigningNames.length === 1 && assigningNames[0] === name;

  return (
    <div className="px-5 py-5 rise">
      <div className="flex items-baseline gap-2 mb-3">
        <span className="ff-mono text-[9.5px] tracking-wide-3 small-caps text-saffron">04 / Departments</span>
        <span className="flex-1 h-px bg-hairline" />
        <span className="ff-mono text-[10px] text-slate-2">
          {counts.mapped}/{counts.all} mapped
        </span>
      </div>

      <div className="text-[11.5px] text-slate leading-relaxed mb-3 space-y-1.5">
        <p className="ff-display italic">
          A department is <span className="text-moss not-italic">Mapped</span> when it's pinned to a topology node
          (entrance, elevator, landmark) — patients get full turn-by-turn directions.
        </p>
        <p className="ff-display italic text-slate-2">
          To map: click <span className="not-italic">Assign</span> on a row, then click any node on the map.
          Or open a node and use <span className="not-italic">+ Map departments</span> from there.
        </p>
      </div>

      <div className="flex items-center gap-2 mb-4">
        <button
          onClick={() => setExtractOpen(true)}
          className="flex-1 h-9 bg-saffron text-paper rounded-sm text-[11px] tracking-wide-2 small-caps flex items-center justify-center gap-2 hover:bg-saff-2 transition-colors"
        >
          <Sparkles size={13} strokeWidth={1.5} /> Extract from URL
        </button>
        <button
          onClick={() => {
            if (drafts.length === 0 || aliasInflight) return;
            expandAliases.mutate(
              { slug },
              { onSuccess: (res) => setAliasJobId(res.job_id) },
            );
          }}
          disabled={drafts.length === 0 || aliasInflight || dirty}
          className={cn(
            "h-9 px-3 rounded-sm text-[10.5px] tracking-wide-2 small-caps border transition-colors flex items-center gap-2",
            drafts.length === 0 || aliasInflight || dirty
              ? "border-hairline text-slate-2 cursor-not-allowed"
              : "border-saffron text-saffron hover:bg-saffron/10",
          )}
          title={
            drafts.length === 0
              ? "Add or extract a department first"
              : dirty
                ? "Save department changes first — the LLM job reads from disk"
                : aliasInflight ? "Expanding aliases…" : "Expand aliases EN+ES for every department"
          }
        >
          {aliasInflight && <Loader2 size={12} className="animate-spin" strokeWidth={1.5} />}
          Aliases
        </button>
      </div>

      {aliasJobId && (
        <div className="mb-4 px-2.5 py-2 bg-paper-2 border border-hairline rounded-sm">
          <div className="flex items-center gap-2 mb-1.5">
            {aliasInflight && <Loader2 size={11} className="animate-spin text-saffron" strokeWidth={1.5} />}
            <span className={cn(
              "ff-mono text-[10px] tracking-wide-2 small-caps",
              aliasJob.status === "failed" ? "text-rust" : aliasJob.status === "complete" ? "text-moss" : "text-saffron",
            )}>
              {aliasJob.status === "failed" ? "Failed" : aliasJob.status === "complete" ? "Done" : aliasJob.stage || "Starting"}
            </span>
            <span className="ml-auto ff-mono text-[10px] text-slate-2">{Math.round(aliasJob.pct * 100)}%</span>
          </div>
          <div className="h-1 rounded-full bg-paper overflow-hidden">
            <div
              className={cn("h-full transition-all duration-300 ease-out",
                aliasJob.status === "failed" ? "bg-rust" : "bg-saffron")}
              style={{ width: `${Math.max(2, aliasJob.pct * 100)}%` }}
            />
          </div>
          {(aliasJob.msg || aliasJob.error) && (
            <p className={cn("ff-mono text-[10.5px] mt-1.5",
              aliasJob.status === "failed" ? "text-rust" : "text-slate")}>
              {aliasJob.error || aliasJob.msg}
            </p>
          )}
        </div>
      )}

      {/* Bulk-by-floor groups */}
      {bulkGroups.length > 0 && (
        <div className="mb-4 space-y-1.5">
          <p className="ff-mono text-[10px] tracking-wide-3 small-caps text-slate-2">
            Bulk map · co-located unmapped
          </p>
          {bulkGroups.map((g) => {
            const isAssigningGroup =
              !!assigningNames &&
              assigningNames.length === g.depts.length &&
              g.depts.every((d) => assigningNames.includes(d.name));
            return (
              <button
                key={g.key}
                onClick={() => {
                  if (isAssigningGroup) {
                    setAssigningNames(null);
                  } else {
                    setAssigningNames(g.depts.map((d) => d.name));
                  }
                }}
                className={cn(
                  "w-full flex items-center gap-2 px-2.5 h-8 rounded-sm border text-[11px] transition-colors",
                  isAssigningGroup
                    ? "border-saffron bg-saffron/10 text-saffron"
                    : "border-hairline text-slate hover:text-ink hover:border-saffron/50 hover:bg-paper-2",
                )}
              >
                <Target size={11} strokeWidth={1.5} />
                <span className="flex-1 text-left truncate">
                  {g.building || "—"}{g.floor ? ` · ${g.floor}` : ""}
                </span>
                <span className="ff-mono text-[10px] text-slate-2">
                  {g.depts.length} unmapped
                </span>
              </button>
            );
          })}
        </div>
      )}

      <div className="relative mb-3">
        <Search size={12} strokeWidth={1.5} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-2" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter by name or building"
          className="w-full bg-paper-2 border border-hairline rounded-sm pl-7 pr-2.5 h-8 text-[12px] outline-none focus:border-saffron"
        />
      </div>

      <div className="flex items-center gap-1.5 mb-3 flex-wrap">
        {(
          [
            ["all",      `All (${counts.all})`],
            ["unmapped", `Unmapped (${counts.unmapped})`],
            ["mapped",   `Mapped (${counts.mapped})`],
            ...(counts.stale > 0 ? ([["stale", `Stale (${counts.stale})`]] as [Filter, string][]) : []),
          ] as [Filter, string][]
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setFilter(k)}
            className={cn(
              "px-2.5 h-6 rounded-sm text-[10.5px] tracking-wide-2 small-caps transition-colors",
              filter === k ? "bg-ink text-paper" : "text-slate hover:text-ink hover:bg-paper-2",
              k === "stale" && filter !== k && "text-rust",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {assigningNames && assigningNames.length > 0 && (
        <div className="mb-3 px-3 py-2 bg-saffron/10 border border-saffron/40 rounded-sm flex items-center gap-2">
          <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron flex-1">
            {assigningNames.length === 1
              ? `Click a node to assign "${assigningNames[0]}"`
              : `Click a node to assign ${assigningNames.length} departments`}
          </span>
          <button
            onClick={() => setAssigningNames(null)}
            className="ff-mono text-[10px] tracking-wide-2 small-caps text-saffron hover:text-saff-2"
          >
            Cancel · Esc
          </button>
        </div>
      )}

      <div className="space-y-1.5">
        {filtered.map((d) => {
          const realIdx = drafts.indexOf(d);
          const isDup = duplicateNames.has(d.name);
          return (
            <DepartmentRow
              key={realIdx}
              dept={d}
              nodes={nodes}
              expanded={expandedIdx === realIdx}
              isDuplicateName={isDup}
              onToggleExpand={() => setExpandedIdx(expandedIdx === realIdx ? null : realIdx)}
              isAssigning={isAssigningSingle(d.name) && !isDup}
              onAssignClick={() => {
                setAssigningNames(isAssigningSingle(d.name) ? null : [d.name]);
              }}
              onUnassign={() => updateDeptAt(realIdx, { topology_node_id: undefined })}
              onDelete={() => {
                if (confirm(`Delete "${d.name}" from this facility?`)) removeDeptAt(realIdx);
              }}
              onPatch={(patch) => updateDeptAt(realIdx, patch)}
              isStale={!!(d.topology_node_id && !nodeIds.has(d.topology_node_id))}
            />
          );
        })}
        {filtered.length === 0 && (
          <p className="ff-mono text-[10.5px] text-slate-2 italic px-2 py-3">
            {search ? "No departments match." : "No departments — run extraction or hand-author them."}
          </p>
        )}
        <button
          onClick={() => {
            const base = "New department";
            let i = 0;
            let name = base;
            while (drafts.some((d) => d.name === name)) {
              i += 1;
              name = `${base} ${i}`;
            }
            setDrafts((arr) => [...arr, { name }]);
            setExpandedIdx(drafts.length);
          }}
          className="w-full px-3 py-2 border border-dashed border-hairline rounded-sm text-[11px] tracking-wide-2 small-caps text-slate-2 hover:text-saffron hover:border-saffron flex items-center justify-center gap-1.5"
        >
          <Plus size={11} strokeWidth={1.5} /> Add department
        </button>
      </div>
      {duplicateNames.size > 0 && (
        <p className="ff-mono text-[10.5px] text-rust mt-2 leading-snug">
          Duplicate name{duplicateNames.size === 1 ? "" : "s"}: {[...duplicateNames].join(", ")}.
          Rename or delete before saving — the backend will reject duplicates.
        </p>
      )}

      <div className="pt-4 border-t border-hairline mt-4 flex items-center gap-2">
        <button
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate({ slug, departments: drafts })}
          className={cn(
            "flex-1 h-9 rounded-sm text-[11px] tracking-wide-2 small-caps transition-colors flex items-center justify-center gap-2",
            dirty
              ? "bg-ink text-paper hover:bg-ink-2"
              : "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed",
          )}
        >
          {save.isPending && <Loader2 size={13} className="animate-spin" strokeWidth={1.5} />}
          {save.isPending
            ? "Saving…"
            : dirty
              ? "Save department changes"
              : save.isSuccess ? "Saved" : "No changes"}
        </button>
      </div>
      {save.isError && (
        <p className="ff-mono text-[10.5px] text-rust mt-2 leading-snug">
          {(save.error as Error).message}
        </p>
      )}

      <div className="pt-3 mt-2 border-t border-hairline ff-mono text-[10.5px] text-slate-2">
        {expandedTotal} alias{expandedTotal === 1 ? "" : "es"} across {drafts.length} department{drafts.length === 1 ? "" : "s"}.
      </div>

      <ExtractDepartmentsModal
        open={extractOpen}
        onClose={() => setExtractOpen(false)}
        slug={slug}
        facilityName={facilityName}
      />
    </div>
  );
}

interface DepartmentRowProps {
  dept: Department;
  nodes: TopologyNode[];
  isAssigning: boolean;
  isStale: boolean;
  isDuplicateName: boolean;
  expanded: boolean;
  onToggleExpand: () => void;
  onAssignClick: () => void;
  onUnassign: () => void;
  onDelete: () => void;
  onPatch: (patch: Partial<Department>) => void;
}

function DepartmentRow({
  dept, nodes, isAssigning, isStale, isDuplicateName, expanded,
  onToggleExpand, onAssignClick, onUnassign, onDelete, onPatch,
}: DepartmentRowProps) {
  const node = dept.topology_node_id ? nodes.find((n) => n.id === dept.topology_node_id) : null;
  const isMapped = !!dept.topology_node_id;
  const [aliasDraft, setAliasDraft] = useState("");

  return (
    <div
      className={cn(
        "px-3 py-2 bg-paper-2 border rounded-sm group transition-colors",
        isAssigning ? "border-saffron"
          : isDuplicateName ? "border-rust/50"
          : isStale ? "border-rust/40"
          : "border-hairline",
      )}
    >
      <div className="flex items-start gap-2">
        <button
          onClick={onToggleExpand}
          className="text-slate-2 hover:text-ink mt-0.5 flex-shrink-0"
          title={expanded ? "Collapse" : "Edit"}
        >
          {expanded ? <ChevronDown size={12} strokeWidth={1.5} /> : <ChevronRight size={12} strokeWidth={1.5} />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[12.5px] truncate">{dept.name}</span>
            {isDuplicateName && (
              <span className="ff-mono text-[9px] tracking-wide-2 small-caps text-rust flex items-center gap-1">
                <AlertTriangle size={9} strokeWidth={1.5} /> dup
              </span>
            )}
            {dept.confidence === "low" && (
              <span className="ff-mono text-[9px] tracking-wide-2 small-caps text-ochre flex items-center gap-1">
                <AlertTriangle size={9} strokeWidth={1.5} /> low conf.
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-[10.5px] text-slate-2 ff-mono">
            {dept.building && <span className="truncate">{dept.building}</span>}
            {dept.building && dept.floor && <span className="text-slate-3">·</span>}
            {dept.floor && <span className="truncate">{dept.floor}</span>}
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 text-[10.5px]">
            {isMapped ? (
              <span className={cn(
                "ff-mono inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm border",
                isStale ? "border-rust/40 text-rust bg-rust/5" : "border-moss/40 text-moss bg-moss/8",
              )}>
                {isStale ? <AlertTriangle size={9} strokeWidth={1.5} /> : <Check size={9} strokeWidth={1.5} />}
                {node ? node.label : dept.topology_node_id}
              </span>
            ) : (
              <span
                className="ff-mono inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm border border-hairline text-slate-2"
                title="No topology node assigned — patients will only see this department's building/floor, not turn-by-turn directions. Click Assign to fix."
              >
                Unmapped
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            onClick={onAssignClick}
            className={cn(
              "px-2 h-6 rounded-sm text-[10px] tracking-wide-2 small-caps transition-colors",
              isAssigning
                ? "bg-saffron text-paper"
                : "border border-hairline text-slate hover:text-ink hover:border-ink",
            )}
          >
            {isAssigning ? "Pick a node…" : isMapped ? "Reassign" : "Assign"}
          </button>
          {isMapped && (
            <button
              onClick={onUnassign}
              className="text-[10px] tracking-wide-2 small-caps text-slate-2 hover:text-rust"
            >
              Unassign
            </button>
          )}
          <button
            onClick={onDelete}
            className="opacity-0 group-hover:opacity-100 text-slate-3 hover:text-rust transition-opacity"
            title="Delete department"
          >
            <Trash2 size={11} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-hairline space-y-2">
          <FieldRow label="Name">
            <input
              value={dept.name}
              onChange={(e) => onPatch({ name: e.target.value })}
              className="w-full bg-paper border border-hairline rounded-sm px-2 h-7 text-[12px] outline-none focus:border-saffron"
            />
          </FieldRow>
          <div className="grid grid-cols-2 gap-2">
            <FieldRow label="Building">
              <input
                value={dept.building ?? ""}
                onChange={(e) => onPatch({ building: e.target.value || undefined })}
                className="w-full bg-paper border border-hairline rounded-sm px-2 h-7 text-[12px] ff-mono outline-none focus:border-saffron"
              />
            </FieldRow>
            <FieldRow label="Floor">
              <input
                value={dept.floor ?? ""}
                onChange={(e) => onPatch({ floor: e.target.value || undefined })}
                className="w-full bg-paper border border-hairline rounded-sm px-2 h-7 text-[12px] ff-mono outline-none focus:border-saffron"
              />
            </FieldRow>
          </div>
          <FieldRow label={`Aliases (${(dept.aliases ?? []).length})`}>
            <div className="flex flex-wrap gap-1 mb-1.5">
              {(dept.aliases ?? []).map((a, i) => (
                <span
                  key={`${a}-${i}`}
                  className="ff-mono text-[10.5px] tracking-wide-2 px-1.5 py-0.5 bg-paper border border-hairline rounded-sm flex items-center gap-1"
                >
                  {a}
                  <button
                    className="text-slate-3 hover:text-rust"
                    onClick={() =>
                      onPatch({
                        aliases: (dept.aliases ?? []).filter((_, ii) => ii !== i),
                      })
                    }
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <input
              value={aliasDraft}
              onChange={(e) => setAliasDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== "Enter" && e.key !== ",") return;
                e.preventDefault();
                const trimmed = aliasDraft.trim().replace(/,$/, "").trim();
                if (!trimmed) return;
                if ((dept.aliases ?? []).includes(trimmed)) {
                  setAliasDraft("");
                  return;
                }
                onPatch({ aliases: [...(dept.aliases ?? []), trimmed] });
                setAliasDraft("");
              }}
              placeholder="add alias + Enter"
              className="ff-mono text-[10.5px] tracking-wide-2 px-2 h-6 border border-dashed border-hairline rounded-sm bg-transparent placeholder:text-slate-3 outline-none focus:border-saffron w-[160px]"
            />
            <p className="mt-1 text-[10.5px] text-slate-2 italic ff-display leading-snug">
              Patient phrasings for the orchestrator's lookup. Run the workspace's <span className="ff-mono not-italic text-ink">Aliases</span> button above to auto-fill EN+ES.
            </p>
          </FieldRow>
          {dept.confidence && (
            <FieldRow label="Confidence">
              <span className="ff-mono text-[10.5px] tracking-wide-2 small-caps text-slate-2">
                {dept.confidence}
              </span>
              {dept.source && (
                <span className="ff-mono text-[10px] text-slate-3 ml-2 truncate">
                  from {dept.source.length > 40 ? dept.source.slice(0, 40) + "…" : dept.source}
                </span>
              )}
            </FieldRow>
          )}
        </div>
      )}
    </div>
  );
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="ff-mono text-[9.5px] tracking-wide-3 small-caps text-slate-2 mb-1">{label}</div>
      {children}
    </div>
  );
}
