import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import type {
  FacilityBuilding,
  FacilityMetadataPayload,
  FacilityParking,
  FacilityTransit,
} from "@/lib/api";
import { useSaveMetadata } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  slug: string;
  /** Full facility object as returned by /facilities/{slug}. */
  facility: Record<string, unknown>;
}

interface Draft {
  name: string;
  address: string;
  type: string;
  main_phone: string;
  campus_description: string;
  buildings: FacilityBuilding[];
  parking: FacilityParking[];
  transit: FacilityTransit[];
}

function fromFacility(f: Record<string, unknown>): Draft {
  return {
    name:               typeof f.name === "string" ? f.name : "",
    address:            typeof f.address === "string" ? f.address : "",
    type:               typeof f.type === "string" ? f.type : "",
    main_phone:         typeof f.main_phone === "string" ? f.main_phone : "",
    campus_description: typeof f.campus_description === "string" ? f.campus_description : "",
    buildings: Array.isArray(f.buildings) ? (f.buildings as FacilityBuilding[]) : [],
    parking:   Array.isArray(f.parking)   ? (f.parking   as FacilityParking[])  : [],
    transit:   Array.isArray(f.transit)   ? (f.transit   as FacilityTransit[])  : [],
  };
}

export function FacilityPanel({ slug, facility }: Props) {
  const initial = useMemo(() => fromFacility(facility), [facility]);
  const [draft, setDraft] = useState<Draft>(initial);
  // Preserve in-progress edits across refetches. Slug change is handled by
  // remounting the panel with `key={slug}` from the parent.
  const lastInitialRef = useRef(initial);
  useEffect(() => {
    const wasClean = JSON.stringify(draft) === JSON.stringify(lastInitialRef.current);
    lastInitialRef.current = initial;
    if (wasClean) setDraft(initial);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);
  void slug; // remount via parent key handles slug changes
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial);

  const save = useSaveMetadata();

  const onSave = () => {
    const payload: FacilityMetadataPayload = {
      name: draft.name,
      address: draft.address || undefined,
      type: draft.type || undefined,
      main_phone: draft.main_phone || undefined,
      campus_description: draft.campus_description || undefined,
      buildings: draft.buildings,
      parking: draft.parking,
      transit: draft.transit,
    };
    save.mutate({ slug, payload });
  };

  // ⌘S support — same custom event the editor dispatches.
  useEffect(() => {
    const handler = () => {
      if (dirty && !save.isPending) onSave();
    };
    window.addEventListener("atlas:save-current-tab", handler);
    return () => window.removeEventListener("atlas:save-current-tab", handler);
  // We intentionally don't include onSave / save here — they capture state
  // by closure. dirty flips when needed; that's enough.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty, draft, slug]);

  return (
    <div className="px-5 py-5 rise space-y-6">
      <div>
        <div className="flex items-baseline gap-2 mb-3">
          <span className="ff-mono text-[9.5px] tracking-wide-3 small-caps text-saffron">05 / Facility</span>
          <span className="flex-1 h-px bg-hairline" />
        </div>
        <p className="text-[12px] text-slate leading-relaxed italic ff-display">
          Identity, address, and the closed list of buildings the
          <span className="ff-mono not-italic mx-1 text-ink">extract-departments</span> job pins
          to. Add a building before extracting if the LLM is dropping departments for not finding
          a match.
        </p>
      </div>

      <Section title="Identity">
        <Field label="Name">
          <input
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            className="w-full bg-paper-2 border border-hairline rounded-sm px-3 h-9 text-[13px] outline-none focus:border-saffron"
          />
        </Field>
        <Field label="Address">
          <input
            value={draft.address}
            onChange={(e) => setDraft({ ...draft, address: e.target.value })}
            className="w-full bg-paper-2 border border-hairline rounded-sm px-3 h-9 text-[12.5px] ff-mono outline-none focus:border-saffron"
          />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Type">
            <input
              value={draft.type}
              onChange={(e) => setDraft({ ...draft, type: e.target.value })}
              placeholder="e.g. Academic medical center"
              className="w-full bg-paper-2 border border-hairline rounded-sm px-3 h-9 text-[12.5px] outline-none focus:border-saffron"
            />
          </Field>
          <Field label="Main phone">
            <input
              value={draft.main_phone}
              onChange={(e) => setDraft({ ...draft, main_phone: e.target.value })}
              placeholder="(555) 123-4567"
              className="w-full bg-paper-2 border border-hairline rounded-sm px-3 h-9 text-[12.5px] ff-mono outline-none focus:border-saffron"
            />
          </Field>
        </div>
        <Field label="Campus description">
          <textarea
            value={draft.campus_description}
            onChange={(e) => setDraft({ ...draft, campus_description: e.target.value })}
            rows={4}
            className="w-full bg-paper-2 border border-hairline rounded-sm p-2.5 text-[12.5px] leading-relaxed resize-none ff-display focus:border-saffron outline-none"
          />
          <p className="mt-1 text-[10.5px] text-slate-2 italic ff-display leading-snug">
            One paragraph. Used as background context the model can pull from when answering
            broader questions about the campus.
          </p>
        </Field>
      </Section>

      <Section
        title={`Buildings (${draft.buildings.length})`}
        action={
          <button
            onClick={() => setDraft({ ...draft, buildings: [...draft.buildings, { name: "New building", lat: 0, lng: 0 }] })}
            className="ff-mono text-[10.5px] tracking-wide-2 small-caps text-saffron hover:text-saff-2 flex items-center gap-1"
          >
            <Plus size={11} strokeWidth={1.5} /> Add
          </button>
        }
      >
        {draft.buildings.length === 0 ? (
          <p className="ff-mono text-[10.5px] text-slate-2 italic">
            No buildings — extract-departments needs at least one to anchor LLM output.
          </p>
        ) : (
          <div className="space-y-1.5">
            {draft.buildings.map((b, i) => (
              <BuildingRow
                key={i}
                building={b}
                onChange={(patch) =>
                  setDraft({ ...draft, buildings: draft.buildings.map((bb, ii) => ii === i ? { ...bb, ...patch } : bb) })
                }
                onDelete={() => {
                  if (confirm(`Delete building "${b.name}"? Departments pinned to it will become orphaned.`)) {
                    setDraft({ ...draft, buildings: draft.buildings.filter((_, ii) => ii !== i) });
                  }
                }}
              />
            ))}
          </div>
        )}
      </Section>

      <Section
        title={`Parking (${draft.parking.length})`}
        action={
          <button
            onClick={() => setDraft({ ...draft, parking: [...draft.parking, { name: "New parking" }] })}
            className="ff-mono text-[10.5px] tracking-wide-2 small-caps text-saffron hover:text-saff-2 flex items-center gap-1"
          >
            <Plus size={11} strokeWidth={1.5} /> Add
          </button>
        }
      >
        {draft.parking.length === 0 ? (
          <p className="ff-mono text-[10.5px] text-slate-2 italic">No parking entries.</p>
        ) : (
          <div className="space-y-1.5">
            {draft.parking.map((p, i) => (
              <ParkingRow
                key={i}
                parking={p}
                onChange={(patch) =>
                  setDraft({ ...draft, parking: draft.parking.map((pp, ii) => ii === i ? { ...pp, ...patch } : pp) })
                }
                onDelete={() => setDraft({ ...draft, parking: draft.parking.filter((_, ii) => ii !== i) })}
              />
            ))}
          </div>
        )}
      </Section>

      {draft.transit.length > 0 && (
        <Section title={`Transit (${draft.transit.length})`}>
          <div className="space-y-1.5">
            {draft.transit.map((t, i) => (
              <TransitRow
                key={i}
                transit={t}
                onChange={(patch) =>
                  setDraft({ ...draft, transit: draft.transit.map((tt, ii) => ii === i ? { ...tt, ...patch } : tt) })
                }
                onDelete={() => setDraft({ ...draft, transit: draft.transit.filter((_, ii) => ii !== i) })}
              />
            ))}
          </div>
        </Section>
      )}

      <div className="pt-4 border-t border-hairline flex items-center gap-2 sticky bottom-0 bg-paper">
        <button
          disabled={!dirty || save.isPending}
          onClick={onSave}
          className={cn(
            "flex-1 h-9 rounded-sm text-[11px] tracking-wide-2 small-caps transition-colors flex items-center justify-center gap-2",
            dirty
              ? "bg-ink text-paper hover:bg-ink-2"
              : "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed",
          )}
        >
          {save.isPending && <Loader2 size={13} className="animate-spin" strokeWidth={1.5} />}
          {save.isPending ? "Saving…" : dirty ? "Save facility" : save.isSuccess ? "Saved" : "No changes"}
        </button>
      </div>
      {save.isError && (
        <p className="ff-mono text-[10.5px] text-rust mt-2 leading-snug">
          {(save.error as Error).message}
        </p>
      )}
    </div>
  );
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="ff-display italic text-[14px]">{title}</span>
        <span className="flex-1 h-px bg-hairline" />
        {action}
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="ff-mono text-[9.5px] tracking-wide-3 small-caps text-slate-2 mb-1">{label}</div>
      {children}
    </div>
  );
}

function BuildingRow({
  building, onChange, onDelete,
}: {
  building: FacilityBuilding;
  onChange: (patch: Partial<FacilityBuilding>) => void;
  onDelete: () => void;
}) {
  return (
    <div className="px-3 py-2 bg-paper-2 border border-hairline rounded-sm group">
      <div className="flex items-center gap-2">
        <input
          value={building.name}
          onChange={(e) => onChange({ name: e.target.value })}
          className="flex-1 bg-paper border border-hairline rounded-sm px-2 h-7 text-[12px] outline-none focus:border-saffron"
        />
        <button
          onClick={onDelete}
          className="opacity-0 group-hover:opacity-100 text-slate-3 hover:text-rust transition-opacity"
          title="Delete building"
        >
          <Trash2 size={11} strokeWidth={1.5} />
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-1.5">
        <input
          value={building.lat}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            if (!Number.isNaN(v)) onChange({ lat: v });
          }}
          placeholder="lat"
          className="bg-paper border border-hairline rounded-sm px-2 h-6 text-[11px] ff-mono outline-none focus:border-saffron"
        />
        <input
          value={building.lng}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            if (!Number.isNaN(v)) onChange({ lng: v });
          }}
          placeholder="lng"
          className="bg-paper border border-hairline rounded-sm px-2 h-6 text-[11px] ff-mono outline-none focus:border-saffron"
        />
      </div>
    </div>
  );
}

function ParkingRow({
  parking, onChange, onDelete,
}: {
  parking: FacilityParking;
  onChange: (patch: Partial<FacilityParking>) => void;
  onDelete: () => void;
}) {
  return (
    <div className="px-3 py-2 bg-paper-2 border border-hairline rounded-sm group">
      <div className="flex items-center gap-2">
        <input
          value={parking.name}
          onChange={(e) => onChange({ name: e.target.value })}
          className="flex-1 bg-paper border border-hairline rounded-sm px-2 h-7 text-[12px] outline-none focus:border-saffron"
        />
        <button
          onClick={onDelete}
          className="opacity-0 group-hover:opacity-100 text-slate-3 hover:text-rust transition-opacity"
          title="Delete parking"
        >
          <Trash2 size={11} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}

function TransitRow({
  transit, onChange, onDelete,
}: {
  transit: FacilityTransit;
  onChange: (patch: Partial<FacilityTransit>) => void;
  onDelete: () => void;
}) {
  return (
    <div className="px-3 py-2 bg-paper-2 border border-hairline rounded-sm group">
      <div className="flex items-center gap-2">
        <input
          value={transit.name}
          onChange={(e) => onChange({ name: e.target.value })}
          className="flex-1 bg-paper border border-hairline rounded-sm px-2 h-7 text-[12px] outline-none focus:border-saffron"
        />
        <button
          onClick={onDelete}
          className="opacity-0 group-hover:opacity-100 text-slate-3 hover:text-rust transition-opacity"
          title="Delete transit"
        >
          <Trash2 size={11} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}
