import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Loader2, Plus, Sparkles, Trash2, X as XIcon } from "lucide-react";
import { queryKeys, useExtractDepartments } from "@/lib/api";
import { useJobStream } from "@/lib/jobs";
import { cn } from "@/lib/utils";

const STAGE_LABEL: Record<string, string> = {
  starting:     "Starting",
  config_ready: "LLM endpoint ready",
  fetching:     "Fetching hospital page",
  fetch_warning: "Fetch warning",
  calling_llm:  "Calling LLM",
  parsing:      "Parsing JSON response",
  merging:      "Merging departments",
};

interface Props {
  open: boolean;
  onClose: () => void;
  slug: string;
  facilityName: string;
}

export function ExtractDepartmentsModal({ open, onClose, slug, facilityName }: Props) {
  const [urls, setUrls] = useState<string[]>([""]);
  const [jobId, setJobId] = useState<string | null>(null);

  const extract = useExtractDepartments();
  const job = useJobStream(jobId);
  const qc = useQueryClient();

  useEffect(() => {
    if (!open) return;
    setUrls([""]);
    setJobId(null);
    extract.reset();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // On complete, refetch the facility so the new departments appear.
  useEffect(() => {
    if (job.status !== "complete") return;
    qc.invalidateQueries({ queryKey: queryKeys.facility(slug) });
    qc.invalidateQueries({ queryKey: queryKeys.facilities });
  }, [job.status, slug, qc]);

  if (!open) return null;

  const inflight = !!jobId && job.status !== "failed" && job.status !== "complete";
  const validUrls = urls.map((u) => u.trim()).filter((u) => u.length > 0);
  const canSubmit = validUrls.length > 0 && !inflight && !extract.isPending;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      const res = await extract.mutateAsync({ slug, urls: validUrls });
      setJobId(res.job_id);
    } catch {
      // Error rendered below.
    }
  };

  const errorText = extract.error?.message ?? job.error ?? null;

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center p-6 bg-ink/40 backdrop-blur-sm rise">
      <div className="bg-paper rounded-sm crisp-shadow-strong w-[640px] max-w-full overflow-hidden">
        <header className="flex items-center justify-between px-6 h-12 border-b border-hairline">
          <div className="flex items-baseline gap-2">
            <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron">
              02 / Extract departments
            </span>
            <span className="ff-display italic text-[15px]">{facilityName}</span>
          </div>
          <button
            onClick={onClose}
            disabled={inflight}
            className="text-slate hover:text-ink disabled:opacity-40"
          >
            <XIcon size={16} strokeWidth={1.5} />
          </button>
        </header>

        {!jobId && (
          <form onSubmit={submit} className="px-6 py-5 space-y-4">
            <div>
              <label className="block ff-mono text-[10px] tracking-wide-3 small-caps text-slate-2 mb-1.5">
                Hospital page URLs
              </label>
              <p className="text-[11.5px] text-slate mb-2 italic ff-display leading-relaxed">
                Paste public-facing pages where departments + locations are listed. The LLM
                constrains its output to your facility's existing buildings list — anything it
                can't pin to a real building is dropped.
              </p>
              <div className="space-y-1.5">
                {urls.map((u, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      autoFocus={i === 0}
                      value={u}
                      onChange={(e) => setUrls((arr) => arr.map((x, ii) => (ii === i ? e.target.value : x)))}
                      placeholder="https://hospital.org/services"
                      className="flex-1 bg-paper-2 border border-hairline rounded-sm px-3 h-9 text-[12.5px] ff-mono outline-none focus:border-saffron"
                    />
                    {urls.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setUrls((arr) => arr.filter((_, ii) => ii !== i))}
                        className="text-slate-3 hover:text-rust"
                        title="Remove this URL"
                      >
                        <Trash2 size={13} strokeWidth={1.5} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setUrls((arr) => [...arr, ""])}
                disabled={urls.length >= 20}
                className="mt-2 ff-mono text-[10.5px] tracking-wide-2 small-caps text-saffron hover:text-saff-2 flex items-center gap-1.5 disabled:text-slate-3"
              >
                <Plus size={11} strokeWidth={1.5} /> Add another URL
              </button>
            </div>

            <div className="bg-paper-2 border border-hairline rounded-sm px-3 py-2">
              <div className="flex items-baseline gap-2">
                <Sparkles size={12} className="text-saffron" strokeWidth={1.5} />
                <span className="ff-display italic text-[13px]">What works best</span>
              </div>
              <p className="text-[11.5px] text-slate mt-1 leading-relaxed ml-5">
                A "Find a service" or "Departments" page; a building-by-building locations page;
                a maps-and-directions page that lists what's where. Fewer URLs of high-signal
                pages beat many URLs of marketing copy.
              </p>
            </div>

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
                disabled={!canSubmit}
                className={cn(
                  "px-4 h-9 rounded-sm text-[11.5px] tracking-wide-2 small-caps flex items-center gap-2 transition-colors",
                  canSubmit
                    ? "bg-ink text-paper hover:bg-ink-2"
                    : "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed",
                )}
              >
                {extract.isPending && <Loader2 size={13} className="animate-spin" strokeWidth={1.5} />}
                Extract from {validUrls.length} URL{validUrls.length === 1 ? "" : "s"}
                <ArrowRight size={13} strokeWidth={1.5} />
              </button>
            </div>
          </form>
        )}

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
              <p className="ff-display text-[18px] leading-snug">
                {STAGE_LABEL[job.stage] ?? job.stage ?? "Starting…"}
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

            {job.status === "complete" && job.result && (
              <div className="border-t border-hairline pt-4 space-y-2">
                <div className="ff-display text-[15px]">
                  Added <span className="text-saffron">{String(job.result.departments_added ?? 0)}</span> departments
                  {!!Number(job.result.departments_dropped ?? 0) && (
                    <span className="text-slate-2 ff-display italic"> · {String(job.result.departments_dropped)} dropped (didn't match a building)</span>
                  )}
                </div>
                <p className="text-[11.5px] text-slate ff-display italic">
                  Refresh the Departments tab to see them. Don't forget to map each one to its
                  entrance node.
                </p>
                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    onClick={onClose}
                    className="px-3 h-9 bg-ink text-paper rounded-sm text-[11px] tracking-wide-2 small-caps"
                  >
                    Close
                  </button>
                </div>
              </div>
            )}

            {job.status === "failed" && (
              <div className="border-t border-hairline pt-4 space-y-2">
                <p className="ff-mono text-[11px] text-rust leading-relaxed">{job.error}</p>
                <div className="flex items-center justify-end gap-2">
                  <button
                    onClick={() => { setJobId(null); extract.reset(); }}
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
