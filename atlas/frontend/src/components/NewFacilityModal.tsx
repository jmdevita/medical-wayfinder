import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Loader2, Sparkles, X as XIcon } from "lucide-react";
import { useBootstrap, queryKeys } from "@/lib/api";
import { useJobStream } from "@/lib/jobs";
import { cn } from "@/lib/utils";

const STAGE_LABEL: Record<string, string> = {
  starting:           "Starting",
  geocoding:          "Geocoding via Nominatim",
  geocoded:           "Address resolved",
  overpass:           "Querying OpenStreetMap",
  overpass_done:      "Raw features fetched",
  filtering:          "Filtering residential noise",
  filtered:           "Relevant features kept",
  building_layers:    "Building OSM reference layer",
  building_facility:  "Building facility.json",
  building_topology:  "Seeding topology nodes",
  writing:            "Writing files",
};

interface Props {
  open: boolean;
  onClose: () => void;
}

export function NewFacilityModal({ open, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [slugOverride, setSlugOverride] = useState("");
  const [includeLandmarks, setIncludeLandmarks] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [resolvedSlug, setResolvedSlug] = useState<string | null>(null);

  const bootstrap = useBootstrap();
  const job = useJobStream(jobId);

  const navigate = useNavigate();
  const qc = useQueryClient();

  // Reset everything when the modal opens or closes.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSlugOverride("");
    setIncludeLandmarks(false);
    setJobId(null);
    setResolvedSlug(null);
    bootstrap.reset();
  // bootstrap is stable across renders; we don't want to re-run on its identity
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // When the job completes, refresh facilities and jump to the editor.
  useEffect(() => {
    if (job.status !== "complete" || !resolvedSlug) return;
    qc.invalidateQueries({ queryKey: queryKeys.facilities });
    const t = setTimeout(() => {
      onClose();
      navigate({ to: "/editor", search: { slug: resolvedSlug } });
    }, 600);
    return () => clearTimeout(t);
  }, [job.status, resolvedSlug, qc, navigate, onClose]);

  if (!open) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || bootstrap.isPending || jobId) return;
    try {
      const res = await bootstrap.mutateAsync({
        query: query.trim(),
        slug: slugOverride.trim() || undefined,
        include_landmarks: includeLandmarks,
      });
      setJobId(res.job_id);
      setResolvedSlug(res.slug);
    } catch {
      // The mutation's error state is rendered below.
    }
  };

  const inflight = !!jobId && job.status !== "failed";
  const errorText = bootstrap.error?.message ?? job.error ?? null;

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center p-6 bg-ink/40 backdrop-blur-sm rise">
      <div className="bg-paper rounded-sm crisp-shadow-strong w-[560px] max-w-full overflow-hidden">
        <header className="flex items-center justify-between px-6 h-12 border-b border-hairline">
          <div className="flex items-baseline gap-2">
            <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron">01 / Locate</span>
            <span className="ff-display italic text-[15px]">Add a hospital</span>
          </div>
          <button onClick={onClose} disabled={inflight} className="text-slate hover:text-ink disabled:opacity-40">
            <XIcon size={16} strokeWidth={1.5} />
          </button>
        </header>

        {/* Form */}
        {!jobId && (
          <form onSubmit={submit} className="px-6 py-5 space-y-5">
            <div>
              <label className="block ff-mono text-[10px] tracking-wide-3 small-caps text-slate-2 mb-1.5">
                Hospital name or address
              </label>
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Brigham and Women's Hospital, Boston"
                className="w-full bg-paper-2 border border-hairline rounded-sm px-3 h-10 text-[13px] outline-none focus:border-saffron"
              />
              <p className="mt-1.5 text-[10.5px] text-slate-2 italic ff-display">
                Used for Nominatim geocoding. The more specific, the better.
              </p>
            </div>

            <div>
              <label className="block ff-mono text-[10px] tracking-wide-3 small-caps text-slate-2 mb-1.5">
                Slug (optional)
              </label>
              <input
                value={slugOverride}
                onChange={(e) => setSlugOverride(e.target.value)}
                placeholder="auto-generated from the name if blank"
                className="w-full bg-paper-2 border border-hairline rounded-sm px-3 h-9 text-[12.5px] ff-mono outline-none focus:border-saffron"
              />
            </div>

            <label className="flex items-start gap-2 text-[12px] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={includeLandmarks}
                onChange={(e) => setIncludeLandmarks(e.target.checked)}
                className="mt-1 accent-saffron"
              />
              <span className="text-ink-2">
                <span className="ff-display italic">Also seed landmark nodes</span>
                <span className="block text-slate-2 text-[11px] ff-display italic mt-0.5">
                  Cafes, shops, pharmacies near the campus. Useful for small urban clinics where
                  patients re-orient by storefronts. Adds noise on big hospital campuses.
                </span>
              </span>
            </label>

            {errorText && (
              <p className="ff-mono text-[10.5px] text-rust">{errorText}</p>
            )}

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-hairline">
              <button
                type="button"
                onClick={onClose}
                className="px-3 h-9 text-[11px] tracking-wide-2 small-caps text-slate hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!query.trim() || bootstrap.isPending}
                className={cn(
                  "px-4 h-9 rounded-sm text-[11.5px] tracking-wide-2 small-caps flex items-center gap-2 transition-colors",
                  query.trim() && !bootstrap.isPending
                    ? "bg-ink text-paper hover:bg-ink-2"
                    : "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed",
                )}
              >
                {bootstrap.isPending && <Loader2 size={13} className="animate-spin" strokeWidth={1.5} />}
                Locate on OSM
                <ArrowRight size={13} strokeWidth={1.5} />
              </button>
            </div>
          </form>
        )}

        {/* Progress */}
        {jobId && (
          <div className="px-6 py-6 space-y-5">
            <div>
              <div className="flex items-baseline gap-2 mb-2">
                <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron">
                  {job.status === "complete" ? "Done" : job.status === "failed" ? "Failed" : "In progress"}
                </span>
                <span className="flex-1 h-px bg-hairline" />
                <span className="ff-mono text-[10px] text-slate-2">{Math.round(job.pct * 100)}%</span>
              </div>
              <p className="ff-display text-[20px] leading-snug">
                {STAGE_LABEL[job.stage] ?? job.stage ?? "Starting…"}
                {resolvedSlug && (
                  <>
                    {" "}
                    <span className="text-saffron italic">{resolvedSlug}</span>
                  </>
                )}
              </p>
              {job.msg && (
                <p className="mt-1.5 text-[11.5px] text-slate-2 ff-mono leading-relaxed">{job.msg}</p>
              )}
            </div>

            <div className="h-1 rounded-full bg-paper-2 overflow-hidden">
              <div
                className={cn(
                  "h-full transition-all duration-500 ease-out",
                  job.status === "failed" ? "bg-rust" : "bg-saffron",
                )}
                style={{ width: `${Math.max(2, job.pct * 100)}%` }}
              />
            </div>

            <ol className="space-y-1 text-[11.5px] text-slate ff-mono">
              {Object.keys(STAGE_LABEL).map((s) => (
                <li
                  key={s}
                  className={cn(
                    "flex items-center gap-2",
                    job.stage === s
                      ? "text-saffron"
                      : isStageDone(job, s)
                        ? "text-moss"
                        : "text-slate-3",
                  )}
                >
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: "currentColor" }} />
                  {STAGE_LABEL[s]}
                </li>
              ))}
            </ol>

            {job.status === "complete" && (
              <div className="border-t border-hairline pt-4 flex items-center gap-2">
                <Sparkles size={14} className="text-saffron" strokeWidth={1.5} />
                <span className="text-[12px] flex-1">Opening the editor for {resolvedSlug}…</span>
                <Loader2 size={13} className="animate-spin text-saffron" strokeWidth={1.5} />
              </div>
            )}

            {job.status === "failed" && (
              <div className="border-t border-hairline pt-4 space-y-2">
                <p className="ff-mono text-[11px] text-rust leading-relaxed">{job.error}</p>
                <div className="flex items-center justify-end gap-2">
                  <button
                    onClick={() => { setJobId(null); setResolvedSlug(null); bootstrap.reset(); }}
                    className="px-3 h-9 border border-hairline text-[11px] tracking-wide-2 small-caps text-slate hover:text-ink rounded-sm"
                  >
                    Try again
                  </button>
                  <button
                    onClick={onClose}
                    className="px-3 h-9 text-[11px] tracking-wide-2 small-caps text-slate hover:text-ink"
                  >
                    Close
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function isStageDone(state: { stage: string; pct: number }, stage: string): boolean {
  // We treat a stage as "done" if the live pct passed its starting threshold.
  const threshold: Record<string, number> = {
    starting: 0.05,
    geocoding: 0.18,
    geocoded: 0.25,
    overpass: 0.55,
    overpass_done: 0.65,
    filtering: 0.74,
    filtered: 0.81,
    building_layers: 0.87,
    building_facility: 0.92,
    building_topology: 0.96,
    writing: 1.0,
  };
  if (state.stage === stage) return false;
  return state.pct >= (threshold[stage] ?? 1);
}
