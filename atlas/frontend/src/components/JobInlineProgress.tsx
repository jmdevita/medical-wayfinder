import { useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";
import { useJobStream } from "@/lib/jobs";
import { cn } from "@/lib/utils";

interface Props {
  jobId: string | null;
  /** Called once when the job transitions to complete or failed. */
  onSettled?: (status: "complete" | "failed", result: Record<string, unknown> | null, error: string | null) => void;
}

/**
 * Compact inline progress widget — used wherever an action kicks off a job
 * but doesn't deserve a full modal. Calls `onSettled` exactly once per job.
 */
export function JobInlineProgress({ jobId, onSettled }: Props) {
  const job = useJobStream(jobId);
  // Track which jobIds we've already notified onSettled for, so a parent
  // re-render after settle doesn't fire the callback again.
  const settledFor = useRef<string | null>(null);

  useEffect(() => {
    if (!jobId) {
      settledFor.current = null;
      return;
    }
    if (job.status !== "complete" && job.status !== "failed") return;
    if (settledFor.current === jobId) return;
    settledFor.current = jobId;
    onSettled?.(job.status, job.result, job.error);
  }, [jobId, job.status, job.result, job.error, onSettled]);

  if (!jobId) return null;

  const isFailed = job.status === "failed";
  const isDone = job.status === "complete";
  const pct = Math.max(2, Math.min(100, job.pct * 100));

  return (
    <div className="mt-3 px-2.5 py-2 bg-paper-2 border border-hairline rounded-sm">
      <div className="flex items-center gap-2 mb-1.5">
        {!isDone && !isFailed && <Loader2 size={11} className="animate-spin text-saffron" strokeWidth={1.5} />}
        <span className={cn(
          "ff-mono text-[10px] tracking-wide-2 small-caps",
          isFailed ? "text-rust" : isDone ? "text-moss" : "text-saffron",
        )}>
          {isFailed ? "Failed" : isDone ? "Done" : (job.stage || "Starting")}
        </span>
        <span className="ml-auto ff-mono text-[10px] text-slate-2">{Math.round(pct)}%</span>
      </div>
      <div className="h-1 rounded-full bg-paper overflow-hidden">
        <div
          className={cn("h-full transition-all duration-300 ease-out", isFailed ? "bg-rust" : "bg-saffron")}
          style={{ width: `${pct}%` }}
        />
      </div>
      {(job.msg || job.error) && (
        <p className={cn(
          "ff-mono text-[10.5px] mt-1.5 leading-snug",
          isFailed ? "text-rust" : "text-slate",
        )}>
          {job.error || job.msg}
        </p>
      )}
    </div>
  );
}
