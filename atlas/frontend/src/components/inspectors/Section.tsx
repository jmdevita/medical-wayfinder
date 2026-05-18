import { type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { useAtlasStore } from "@/lib/store";
import { cn } from "@/lib/utils";

interface Props {
  /** "node" or "edge" — keys section state per inspector kind. */
  kind: "node" | "edge";
  /** node id or edge key (`${from}__${to}`). */
  subjectId: string;
  /** Stable section name within this kind, e.g. "photos", "drafts". */
  name: string;
  title: string;
  /** Right-aligned summary chip (count, status, etc.). Pass null to hide. */
  count?: ReactNode;
  /** Default open state when no per-subject preference has been recorded. */
  defaultOpen?: boolean;
  children: ReactNode;
}

/**
 * Collapsible inspector section. Mirrors the `<details>`-style chrome from
 * docs/30-editor-redesign-mockup.html but stores the open/closed bit in the
 * Zustand store keyed by subject so the user's choices persist across
 * inspector swaps.
 */
export function Section({
  kind, subjectId, name, title, count, defaultOpen = false, children,
}: Props) {
  const key = `${kind}:${subjectId}:${name}`;
  const recorded = useAtlasStore((s) => s.inspectorSections[key]);
  const setOpen = useAtlasStore((s) => s.setInspectorSection);
  const open = recorded ?? defaultOpen;

  return (
    <div className="border-b border-hairline py-3">
      <button
        type="button"
        onClick={() => setOpen(key, !open)}
        className="w-full flex items-center gap-2 text-left ff-mono text-[10.5px] tracking-wide-3 small-caps text-slate hover:text-ink transition-colors"
      >
        <ChevronRight
          size={11}
          strokeWidth={1.5}
          className={cn("text-slate-2 transition-transform", open && "rotate-90")}
        />
        <span className={cn(open && "text-ink")}>{title}</span>
        {count !== undefined && count !== null && (
          <span className="ml-auto ff-mono text-[10px] bg-paper-2 text-slate px-2 py-0.5 rounded-full">
            {count}
          </span>
        )}
      </button>
      {open && <div className="pt-3 pb-1">{children}</div>}
    </div>
  );
}
