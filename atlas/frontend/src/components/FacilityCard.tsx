import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import type { FacilityMeta } from "@/lib/types";
import { STATUS_META } from "@/lib/topology-meta";
import { useAtlasStore } from "@/lib/store";
import { MiniMap } from "./MiniMap";
import { NewFacilityModal } from "./NewFacilityModal";
import { StatusDot } from "./ui/StatusDot";
import { Stat } from "./ui/Stat";

export function FacilityCard({ f }: { f: FacilityMeta }) {
  const navigate = useNavigate();
  const setActive = useAtlasStore((s) => s.setActiveFacility);

  const handleOpen = () => {
    setActive(f);
    navigate({ to: "/editor", search: { slug: f.id } });
  };

  const s = STATUS_META[f.status];
  const showPulse = f.status === "draft" || f.status === "bootstrap";

  return (
    <button
      onClick={handleOpen}
      className="group text-left bg-paper rounded-sm overflow-hidden crisp-shadow lift"
    >
      <div className="relative h-36 border-b border-hairline overflow-hidden">
        <MiniMap data={f.miniMap} className="absolute inset-0 w-full h-full" />
        <div className="absolute top-2.5 left-2.5">
          <span
            className={
              "inline-flex items-center gap-1.5 px-2 py-0.5 bg-paper/90 backdrop-blur-sm border border-hairline rounded-sm text-[10px] tracking-wide-2 small-caps " +
              s.text
            }
          >
            <StatusDot color={s.dot} pulse={showPulse} /> {s.label}
          </span>
        </div>
        <div className="absolute bottom-2 right-2 ff-mono text-[9px] tracking-wide-2 text-slate-2">
          {f.miniMap.lat.toFixed(3)}° N · {Math.abs(f.miniMap.lng).toFixed(3)}° W
        </div>
      </div>

      <div className="p-4 space-y-3">
        <div>
          <div className="flex items-baseline gap-2 mb-0.5">
            <span className="ff-mono text-[10px] tracking-wide-2 text-slate-2">{f.region.toUpperCase()}</span>
            <span className="h-px flex-1 bg-hairline" />
          </div>
          <h3 className="ff-display text-[18px] leading-tight">{f.name}</h3>
          <p className="ff-mono text-[10.5px] text-slate mt-1">{f.address}</p>
          <p className="text-[11px] italic text-slate-2 mt-0.5 ff-display">{f.type}</p>
        </div>

        <div className="grid grid-cols-3 gap-1 pt-2 border-t border-hairline/70">
          <Stat n={f.nodes} label="Nodes" />
          <Stat n={f.edges} label="Edges" warn={f.edges === 0} />
          <Stat n={f.depts} label="Depts" warn={f.depts === 0} />
        </div>

        <NextStepHint f={f} />

        <div className="pt-2 flex items-center justify-between text-[10.5px] text-slate-2 ff-mono">
          <span>Updated {f.updated}</span>
          <span>by {f.by}</span>
        </div>
      </div>
    </button>
  );
}

function NextStepHint({ f }: { f: FacilityMeta }) {
  const hint = deriveNextStep(f);
  if (!hint) return null;
  return (
    <div className="flex items-center gap-2 px-2.5 h-7 bg-saffron/8 border border-saffron/30 rounded-sm">
      <span className="ff-mono text-[9.5px] tracking-wide-3 small-caps text-saffron">Next</span>
      <span className="text-[11.5px] text-ink-2 italic ff-display flex-1 truncate">{hint}</span>
      <ArrowRight size={11} strokeWidth={1.5} className="text-saffron flex-shrink-0" />
    </div>
  );
}

function deriveNextStep(f: FacilityMeta): string | null {
  if (f.nodes === 0)               return "Locate on OSM";
  if (f.depts === 0)               return "Extract departments from a URL";
  if (f.edges === 0)               return "Draft missing edges";
  // Status-based hints take priority once the basics are in place.
  if (f.status === "review")       return "Resolve validator issues";
  if (f.status === "draft")        return "Author edge prose, then publish";
  if (f.status === "bootstrap")    return "Author edges, map departments";
  return null; // published & clean — no hint needed
}

export function NewFacilityCard() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="group text-left bg-paper border-2 border-dashed border-hairline hover:border-saffron rounded-sm overflow-hidden transition-colors"
      >
        <div className="relative h-36 plate-dots flex items-center justify-center border-b border-dashed border-hairline group-hover:border-saffron transition-colors">
          <div className="grid place-items-center w-12 h-12 rounded-full bg-paper border border-hairline group-hover:border-saffron group-hover:bg-saffron/5 transition-colors">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-slate group-hover:text-saffron">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </div>
        </div>
        <div className="p-4 space-y-2.5">
          <h3 className="ff-display italic text-[19px] leading-tight">Add a hospital</h3>
          <p className="text-[12px] text-slate leading-relaxed">
            Paste a name or address. Atlas pulls buildings, parking, transit, and surrounding landmarks
            from OpenStreetMap, then opens the editor.
          </p>
          <div className="flex items-center gap-2 px-2.5 h-8 bg-paper-2 border border-hairline rounded-sm">
            <span className="ff-mono text-[10.5px] text-slate-2">Try:</span>
            <span className="text-[12px] italic ff-display">Brigham and Women's Hospital, Boston</span>
          </div>
        </div>
      </button>
      <NewFacilityModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}
