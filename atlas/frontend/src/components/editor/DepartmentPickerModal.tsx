import { useMemo, useState } from "react";
import { Check, MapPin, Search, X as XIcon } from "lucide-react";
import type { Department } from "@/lib/api";
import type { TopologyNode } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
  /** The node these depts will be mapped to. */
  node: TopologyNode;
  /** All departments, both mapped and unmapped. */
  departments: Department[];
  /** Apply the mapping (one or many depts → this node) and close. */
  onMap: (deptNames: string[], nodeId: string) => void;
}

/**
 * Inline picker that maps one or more departments to a single node from the
 * node-inspector side. Multi-select; unmapped departments float to the top
 * since they're the most common target. Already-mapped depts can be
 * re-mapped (their previous binding is overwritten).
 *
 * Companion to the existing "Assign → click on map" gesture in
 * DepartmentsPanel — both write into the same lifted draft state.
 */
export function DepartmentPickerModal({
  open, onClose, node, departments, onMap,
}: Props) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const match = (d: Department) =>
      !q ||
      d.name.toLowerCase().includes(q) ||
      (d.building?.toLowerCase().includes(q) ?? false) ||
      (d.floor?.toLowerCase().includes(q) ?? false);
    const sorted = [...departments].filter(match).sort((a, b) => {
      const am = !!a.topology_node_id;
      const bm = !!b.topology_node_id;
      if (am !== bm) return am ? 1 : -1; // unmapped first
      return a.name.localeCompare(b.name);
    });
    return sorted;
  }, [departments, search]);

  if (!open) return null;

  const toggle = (name: string) => {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };
  const submit = () => {
    if (selected.size === 0) return;
    onMap([...selected], node.id);
    setSelected(new Set());
    setSearch("");
    onClose();
  };
  const cancel = () => {
    setSelected(new Set());
    setSearch("");
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center p-6 bg-ink/40 backdrop-blur-sm"
      onClick={cancel}
    >
      <div
        className="bg-paper rounded-sm crisp-shadow-strong w-[520px] max-w-full overflow-hidden flex flex-col max-h-[85vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-5 h-12 border-b border-hairline">
          <div className="flex items-baseline gap-2">
            <MapPin size={13} className="text-saffron" strokeWidth={1.5} />
            <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron">
              Map departments to node
            </span>
            <span className="ff-display italic text-[14px] text-slate-2">{node.label}</span>
          </div>
          <button
            onClick={cancel}
            className="text-slate hover:text-ink"
          >
            <XIcon size={16} strokeWidth={1.5} />
          </button>
        </header>

        <div className="px-5 pt-4 pb-2">
          <div className="relative">
            <Search size={12} strokeWidth={1.5} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-2" />
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter by name, building, or floor"
              className="w-full bg-paper-2 border border-hairline rounded-sm pl-7 pr-2.5 h-9 text-[12.5px] outline-none focus:border-saffron"
            />
          </div>
          <p className="ff-mono text-[10.5px] text-slate-2 italic mt-1.5 leading-snug">
            Pick one or many. Already-mapped departments will be remapped to this node.
          </p>
        </div>

        <ul className="px-2 pb-2 overflow-y-auto flex-1 space-y-1">
          {filtered.length === 0 && (
            <li className="ff-mono text-[11px] text-slate-2 italic px-3 py-3">
              No departments match.
            </li>
          )}
          {filtered.map((d) => {
            const isSel = selected.has(d.name);
            const mapped = !!d.topology_node_id;
            const sub =
              [d.building, d.floor].filter(Boolean).join(" · ") ||
              (mapped ? "currently mapped elsewhere" : "");
            return (
              <li key={d.name}>
                <button
                  onClick={() => toggle(d.name)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 h-11 rounded-sm border text-left transition-colors",
                    isSel
                      ? "border-saffron bg-saffron/10"
                      : "border-transparent hover:bg-paper-2",
                  )}
                >
                  <span
                    className={cn(
                      "w-4 h-4 rounded-sm border flex items-center justify-center flex-shrink-0",
                      isSel ? "bg-saffron border-saffron text-paper" : "border-hairline",
                    )}
                  >
                    {isSel && <Check size={11} strokeWidth={2} />}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[12.5px] truncate">{d.name}</div>
                    {sub && (
                      <div className="ff-mono text-[10px] text-slate-2 truncate">{sub}</div>
                    )}
                  </div>
                  {mapped && (
                    <span className="ff-mono text-[9.5px] tracking-wide-2 small-caps text-moss flex-shrink-0">
                      mapped
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>

        <footer className="flex items-center justify-between gap-2 px-5 h-12 border-t border-hairline bg-paper-2">
          <span className="ff-mono text-[10.5px] text-slate-2">
            {selected.size === 0
              ? "Nothing selected"
              : `${selected.size} selected`}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={cancel}
              className="px-3 h-8 text-[11px] tracking-wide-2 small-caps text-slate hover:text-ink"
            >
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={selected.size === 0}
              className={cn(
                "px-4 h-8 rounded-sm text-[11.5px] tracking-wide-2 small-caps transition-colors",
                selected.size > 0
                  ? "bg-saffron text-paper hover:bg-saff-2"
                  : "bg-paper text-slate-2 border border-hairline cursor-not-allowed",
              )}
            >
              Map {selected.size > 0 ? `${selected.size} ` : ""}to {node.label.length > 16 ? node.label.slice(0, 16) + "…" : node.label}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
