import { useMemo, useState } from "react";
import { useFacilities, useWhoAmI } from "@/lib/api";
import type { FacilityMeta, FacilityStatus } from "@/lib/types";
import { FacilityCard, NewFacilityCard } from "@/components/FacilityCard";
import { StatBig } from "@/components/ui/Stat";
import { SmallCaps } from "@/components/ui/SmallCaps";

type Filter = "all" | "boston" | "la" | "draft" | "review" | "published";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all",       label: "All" },
  { key: "boston",    label: "Boston" },
  { key: "la",        label: "Los Angeles" },
  { key: "draft",     label: "Draft & new" },
  { key: "review",    label: "In review" },
  { key: "published", label: "Published" },
];

function matchesFilter(status: FacilityStatus, region: string, filter: Filter) {
  switch (filter) {
    case "all":       return true;
    case "draft":     return status === "draft" || status === "bootstrap";
    case "review":    return status === "review";
    case "published": return status === "published";
    case "boston":    return region === "Boston";
    case "la":        return region === "Los Angeles";
  }
}

export function FacilitiesView() {
  const [filter, setFilter] = useState<Filter>("all");
  const { data: facilities, isPending, isError, error, refetch } = useFacilities();
  const { data: who } = useWhoAmI();
  const role = who?.role ?? "viewer";
  // Only the trusted tier (facility_editor + admin) sees in-progress drafts
  // and bootstraps. Viewers and contributors see published facilities only —
  // exposing half-built work to the public clutters the home page and leaks
  // work-in-progress edits.
  const seesDrafts = role === "facility_editor" || role === "admin";
  const visible = useMemo(
    () => (facilities ?? []).filter((f) => seesDrafts || f.status === "published"),
    [facilities, seesDrafts],
  );

  const filtered = useMemo(
    () => visible.filter((f) => matchesFilter(f.status, f.region, filter)),
    [visible, filter],
  );

  const totals = useMemo(() => deriveTotals(facilities ?? []), [facilities]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-12 py-10 max-w-[1480px] mx-auto rise">
        <div className="grid grid-cols-12 gap-8 mb-12">
          <div className="col-span-7">
            <div className="flex items-baseline gap-3 mb-3">
              <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron">Atlas / Facilities</span>
              <span className="h-px flex-1 bg-hairline" />
              <span className="ff-mono text-[10px] tracking-wide-2 text-slate-2">
                {totals.count} hospitals · {totals.regionCount} regions
              </span>
            </div>
            <h1 className="ff-display text-[40px] leading-[1.1] tracking-tight">
              Hospital wayfinding,
              <br />
              <span className="italic">edited by the community.</span>
            </h1>
            <p className="mt-5 max-w-[480px] text-[14.5px] leading-relaxed text-ink-2">
              Add or edit a hospital. Map its buildings, entrances, parking, and
              the walking paths between them. Submissions ship to the Wayfinder
              patient app after review.
            </p>
          </div>

          <div className="col-span-5 grid grid-cols-2 gap-x-6 gap-y-4 self-end pb-2">
            <StatBig n={String(totals.nodes)}      label="Total nodes"     sub={`across ${totals.count} facilities`} />
            <StatBig n={String(totals.edges)}      label="Edges authored"  sub={totals.edgesPct} />
            <StatBig n={String(totals.depts)}      label="Departments"     sub="mapped to entrances" />
            <StatBig n={String(totals.regionCount)} label="Regions"        sub="active in this workspace" />
          </div>
        </div>

        <div className="flex items-center gap-2 mb-6 pb-3 border-b border-hairline">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={
                "px-3 h-7 rounded-sm text-[11.5px] tracking-wide-2 small-caps transition-colors " +
                (filter === key ? "bg-ink text-paper" : "text-slate hover:text-ink hover:bg-paper-2")
              }
            >
              {label}
            </button>
          ))}
          <span className="ml-auto text-[10.5px] ff-mono tracking-wide-2 text-slate-2">
            Sort: <span className="text-ink underline decoration-dotted underline-offset-2">recently edited</span>
          </span>
        </div>

        {isPending && <LoadingGrid />}
        {isError && <ErrorBanner message={error.message} onRetry={() => refetch()} />}
        {!isPending && !isError && (
          <div className="grid grid-cols-3 gap-6">
            {filtered.map((f) => <FacilityCard key={f.id} f={f} />)}
            {seesDrafts && <NewFacilityCard />}
          </div>
        )}

        <div className="mt-16 pt-6 border-t border-hairline grid grid-cols-12 gap-8">
          <div className="col-span-3">
            <SmallCaps>How it works</SmallCaps>
            <p className="text-[13px] text-slate leading-relaxed mt-2">
              Four stages from a hospital name to a reviewed entry the patient app can use.
            </p>
          </div>
          <div className="col-span-9 grid grid-cols-4 gap-6">
            <PipelineStep n="01" title="Locate"    body="Fetch buildings, parking, and transit stops from OpenStreetMap." />
            <PipelineStep n="02" title="Extract"   body="Pull department lists from the facility's website." />
            <PipelineStep n="03" title="Author"    body="Draw walking paths and write directions for each entrance." />
            <PipelineStep n="04" title="Publish"   body="Submit for review. Approved facilities ship to the patient app." />
          </div>
        </div>
      </div>
    </div>
  );
}

function deriveTotals(facilities: FacilityMeta[]) {
  const nodes = facilities.reduce((s, f) => s + f.nodes, 0);
  const edges = facilities.reduce((s, f) => s + f.edges, 0);
  const depts = facilities.reduce((s, f) => s + f.depts, 0);
  const expectedEdges = facilities.reduce((s, f) => s + Math.max(f.nodes - 1, 0), 0);
  const pct = expectedEdges ? Math.round((edges / expectedEdges) * 100) : 0;
  const regions = new Set(facilities.map((f) => f.region));
  return {
    nodes, edges, depts,
    count: facilities.length,
    regionCount: regions.size,
    edgesPct: expectedEdges ? `${pct}% of expected` : "—",
  };
}

function LoadingGrid() {
  return (
    <div className="grid grid-cols-3 gap-6">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="bg-paper rounded-sm crisp-shadow overflow-hidden">
          <div className="h-36 plate-dots opacity-60" />
          <div className="p-4 space-y-3">
            <div className="h-3 w-16 bg-paper-2 rounded" />
            <div className="h-5 w-3/4 bg-paper-2 rounded" />
            <div className="h-3 w-2/3 bg-paper-2 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="border border-rust/40 bg-rust/5 rounded-sm p-5">
      <div className="flex items-baseline gap-2 mb-2">
        <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-rust">Backend unreachable</span>
        <span className="flex-1 h-px bg-rust/30" />
      </div>
      <p className="ff-display text-[16px] mb-1">Couldn't load facilities from the API.</p>
      <p className="ff-mono text-[11px] text-slate leading-relaxed mb-3">{message}</p>
      <p className="text-[12px] text-ink-2 mb-3">
        Make sure the backend is running: <span className="ff-mono text-saffron">cd atlas && make dev-backend</span>.
      </p>
      <button onClick={onRetry} className="px-3 h-8 bg-ink text-paper text-[11px] tracking-wide-2 small-caps rounded-sm">
        Retry
      </button>
    </div>
  );
}

function PipelineStep({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-2">
        <span className="ff-mono text-[10px] tracking-wide-3 text-saffron">{n}</span>
        <span className="ff-display italic text-[15px]">{title}</span>
      </div>
      <p className="text-[12px] text-slate leading-relaxed">{body}</p>
    </div>
  );
}
